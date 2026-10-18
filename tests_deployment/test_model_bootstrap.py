"""No live GitHub calls or private credentials: test the pinned Release bootstrap."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import httpx
import model_bootstrap as boot


class ModelBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'app'
        self.root.mkdir()
        self.archive = self.base / 'models.zip'
        self.name = 'backend/app/ai/nlu/model/model.onnx'
        with ZipFile(self.archive, 'w') as z:
            z.writestr(self.name, b'test-model-data')
        data = self.archive.read_bytes()
        self.manifest = {
            'repository': 'owner/project', 'release_tag': 'botkeep-models-v1',
            'asset_name': 'models.zip', 'archive_size': len(data),
            'archive_sha256': hashlib.sha256(data).hexdigest(),
            'files': {self.name: {'size': 15, 'sha256': hashlib.sha256(b'test-model-data').hexdigest()}}
        }

    def write_manifest(self):
        p = self.root / 'deploy/botkeep/model-bundle.json'
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps(self.manifest))

    def test_valid_install_is_byte_exact(self):
        boot.install_archive(self.root, self.archive, self.manifest)
        self.assertTrue(boot.installed(self.root, self.manifest))

    def test_archive_corruption_rejected_before_writes(self):
        self.archive.write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
            boot.install_archive(self.root, self.archive, self.manifest)
        self.assertFalse((self.root / self.name).exists())

    def test_inner_hash_mismatch_rejected(self):
        self.manifest['files'][self.name]['sha256'] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
            boot.install_archive(self.root, self.archive, self.manifest)
        self.assertFalse((self.root / self.name).exists())

    def test_manifest_traversal_rejected(self):
        self.manifest['files'] = {'../../escape': {'size': 1, 'sha256': '0' * 64}}
        with self.assertRaisesRegex(RuntimeError, 'Unsafe'):
            boot.destinations(self.root, self.manifest)

    def test_existing_symlink_rejected(self):
        (self.root / 'backend').symlink_to(self.base, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'symlink'):
            boot.destinations(self.root, self.manifest)

    def test_extra_zip_entry_rejected(self):
        with ZipFile(self.archive, 'a') as z:
            z.writestr('unexpected', b'x')
        self.manifest['archive_size'] = self.archive.stat().st_size
        self.manifest['archive_sha256'] = boot.sha256(self.archive)
        with self.assertRaisesRegex(RuntimeError, 'Unexpected'):
            boot.install_archive(self.root, self.archive, self.manifest)

    def test_cache_restores_without_network(self):
        self.write_manifest()
        data = self.base / 'persistent'
        cache = data / 'model-cache/models.zip'
        cache.parent.mkdir(parents=True)
        cache.write_bytes(self.archive.read_bytes())
        with patch.dict(os.environ, {'DATA_DIR': str(data)}), patch.object(boot, 'download_archive', side_effect=AssertionError('network used')):
            boot.ensure_models(self.root)
        self.assertTrue(boot.installed(self.root, self.manifest))

    def test_verified_installed_models_do_not_download(self):
        self.write_manifest()
        boot.install_archive(self.root, self.archive, self.manifest)
        with patch.object(boot, 'download_archive', side_effect=AssertionError('network used')):
            boot.ensure_models(self.root)

    def test_failed_download_does_not_start_cloud_fallback(self):
        self.write_manifest()
        with patch.dict(os.environ, {'DATA_DIR': str(self.base / 'data')}), patch.object(boot, 'download_archive', side_effect=RuntimeError('unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'No cloud-only fallback'):
                boot.ensure_models(self.root)

    def download(self, handler, token=''):
        original = httpx.Client
        def client(**kwargs):
            return original(transport=httpx.MockTransport(handler), **kwargs)
        with patch.dict(os.environ, {'MODEL_GITHUB_REPO': 'owner/project', 'MODEL_GITHUB_TOKEN': token}), patch('httpx.Client', side_effect=client):
            boot.download_archive(self.base / 'download.zip', self.manifest)

    def test_private_download_auth_not_forwarded_to_asset_cdn(self):
        def handler(request):
            if request.url.host == 'api.github.com':
                self.assertEqual(request.headers.get('authorization'), 'Bearer test-only')
                if '/releases/tags/' in request.url.path:
                    return httpx.Response(200, json={'assets': [{'id': 42, 'name': 'models.zip', 'size': self.manifest['archive_size']}]})
                return httpx.Response(302, headers={'location': 'https://release-assets.githubusercontent.com/test'})
            self.assertNotIn('authorization', request.headers)
            return httpx.Response(200, content=self.archive.read_bytes())
        self.download(handler, token='test-only')
        self.assertEqual(boot.sha256(self.base / 'download.zip'), self.manifest['archive_sha256'])

    def test_wrong_repository_or_token_http_error(self):
        with self.assertRaisesRegex(RuntimeError, 'HTTP 404'):
            self.download(lambda request: httpx.Response(404))

    def test_unexpected_asset_size_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'size differs'):
            self.download(lambda request: httpx.Response(200, json={'assets': [{'name': 'models.zip', 'size': 1, 'id': 42}]}))

    def test_corrupt_download_never_becomes_cache(self):
        def handler(request):
            if '/releases/tags/' in request.url.path:
                return httpx.Response(200, json={'assets': [{'id': 42, 'name': 'models.zip', 'size': self.manifest['archive_size']}]})
            return httpx.Response(200, content=b'bad')
        with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
            self.download(handler)
        self.assertFalse((self.base / 'download.zip').exists())
        self.assertFalse((self.base / 'download.partial').exists())


    def fake_app(self, reader):
        from types import SimpleNamespace
        from unittest.mock import Mock
        local = type('LocalExplainerLLM', (), {})()
        ctx = SimpleNamespace(
            assistant=SimpleNamespace(_reader=reader, _policy=object(), _llm=local),
            reviews=SimpleNamespace(_scorer=object()),
            settings=SimpleNamespace(assistant_cloud_enabled=False, llm_provider=None),
            db=SimpleNamespace(dispose=Mock()),
        )
        return SimpleNamespace(state=SimpleNamespace(ctx=ctx))

    def test_required_reader_failure_stops_startup(self):
        import main
        app = self.fake_app(None)
        with patch('app.hosting.create_app', return_value=app):
            with self.assertRaisesRegex(RuntimeError, 'Required local models'):
                main.create_app()
        app.state.ctx.db.dispose.assert_called_once()

    def test_all_models_present_allows_startup(self):
        import main
        app = self.fake_app(object())
        with patch('app.hosting.create_app', return_value=app):
            self.assertIs(main.create_app(), app)


if __name__ == '__main__':
    unittest.main()
