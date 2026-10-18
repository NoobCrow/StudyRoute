// Runs after `npm install` / `npm ci`.
//
// The production policy is `style-src 'self'`: no inline <style> element may be added. Two libraries add
// one when they load or when a menu, dialog or select opens, so each is changed to ship its CSS another way.
// Both changes are idempotent and fail loudly if the library's code changes.
//
//   sonner                  injected its CSS as a <style> element at load. The same CSS is imported as a
//                           file instead (app/globals.css imports sonner/dist/styles.css).
//   react-style-singleton   (used by Radix to lock page scroll while a dialog or select is open) added a
//                           <style> element. It now adopts a constructable stylesheet, which the policy
//                           does not restrict, and falls back to doing nothing where that is unsupported.
//   input-otp              (the one-time-code boxes) creates a <style id="input-otp-style"> element and inserts
//                           five rules into it. The element is not created; the rules are in app/globals.css.
//   @radix-ui/react-select  renders a <style> element in every open select to hide the scrollbar. The
//                           element is removed and the same two rules are in app/globals.css.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const MODULES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "node_modules");

// --- sonner ------------------------------------------------------------------------------------
const GUARD = "if (!code || typeof document == 'undefined') return";
const DISABLED = "return /* StudyRoute: no inline <style> (CSP); CSS is imported as a file */";

for (const name of ["index.mjs", "index.js"]) {
  const file = path.join(MODULES, "sonner", "dist", name);
  if (!fs.existsSync(file)) continue;
  const source = fs.readFileSync(file, "utf8");
  if (source.includes(DISABLED)) continue;
  if (!source.includes(GUARD))
    throw new Error(`sonner ${name} changed: update scripts/postinstall.mjs`);
  fs.writeFileSync(file, source.replace(GUARD, DISABLED), "utf8");
  console.log(`sonner ${name}: inline style injection disabled`);
}

// --- react-style-singleton ---------------------------------------------------------------------
const MARK = "StudyRoute: constructable stylesheet";

const ESM = `// ${MARK} (no inline <style>, so style-src 'self' holds)
function makeSheet() {
    if (typeof document === 'undefined' || typeof CSSStyleSheet === 'undefined' || !('adoptedStyleSheets' in document))
        return null;
    try {
        return new CSSStyleSheet();
    }
    catch (error) {
        return null;
    }
}
export var stylesheetSingleton = function () {
    var counter = 0;
    var stylesheet = null;
    return {
        add: function (style) {
            if (counter == 0) {
                stylesheet = makeSheet();
                if (stylesheet) {
                    stylesheet.replaceSync(style);
                    document.adoptedStyleSheets = document.adoptedStyleSheets.concat(stylesheet);
                }
            }
            counter++;
        },
        remove: function () {
            counter--;
            if (!counter && stylesheet) {
                var gone = stylesheet;
                document.adoptedStyleSheets = document.adoptedStyleSheets.filter(function (sheet) { return sheet !== gone; });
                stylesheet = null;
            }
        },
    };
};
`;

const CJS = `"use strict";
// ${MARK} (no inline <style>, so style-src 'self' holds)
Object.defineProperty(exports, "__esModule", { value: true });
exports.stylesheetSingleton = void 0;
function makeSheet() {
    if (typeof document === 'undefined' || typeof CSSStyleSheet === 'undefined' || !('adoptedStyleSheets' in document))
        return null;
    try {
        return new CSSStyleSheet();
    }
    catch (error) {
        return null;
    }
}
var stylesheetSingleton = function () {
    var counter = 0;
    var stylesheet = null;
    return {
        add: function (style) {
            if (counter == 0) {
                stylesheet = makeSheet();
                if (stylesheet) {
                    stylesheet.replaceSync(style);
                    document.adoptedStyleSheets = document.adoptedStyleSheets.concat(stylesheet);
                }
            }
            counter++;
        },
        remove: function () {
            counter--;
            if (!counter && stylesheet) {
                var gone = stylesheet;
                document.adoptedStyleSheets = document.adoptedStyleSheets.filter(function (sheet) { return sheet !== gone; });
                stylesheet = null;
            }
        },
    };
};
exports.stylesheetSingleton = stylesheetSingleton;
`;

for (const [folder, replacement] of [
  ["es2015", ESM],
  ["es2019", ESM],
  ["es5", CJS],
]) {
  const file = path.join(MODULES, "react-style-singleton", "dist", folder, "singleton.js");
  if (!fs.existsSync(file)) continue;
  const source = fs.readFileSync(file, "utf8");
  if (source.includes(MARK)) continue;
  if (!source.includes("makeStyleTag"))
    throw new Error(`react-style-singleton ${folder} changed: update scripts/postinstall.mjs`);
  fs.writeFileSync(file, replacement, "utf8");
  console.log(`react-style-singleton ${folder}: uses a constructable stylesheet`);
}

// --- @radix-ui/react-select --------------------------------------------------------------------
const STYLE_BLOCK =
  /(?:\/\* @__PURE__ \*\/ )?(?:\(0, [\w$.]+\)|jsx)\(\s*"style",\s*\{\s*dangerouslySetInnerHTML: \{\s*__html: `\[data-radix-select-viewport\][^`]*`\s*\},\s*nonce\s*\}\s*\)/;

for (const name of ["index.mjs", "index.js"]) {
  const file = path.join(MODULES, "@radix-ui", "react-select", "dist", name);
  if (!fs.existsSync(file)) continue;
  const source = fs.readFileSync(file, "utf8");
  if (!source.includes("data-radix-select-viewport]{")) continue; // already removed
  if (!STYLE_BLOCK.test(source))
    throw new Error(`@radix-ui/react-select ${name} changed: update scripts/postinstall.mjs`);
  fs.writeFileSync(
    file,
    source.replace(
      STYLE_BLOCK,
      "null /* StudyRoute: no inline <style> (CSP); the rules are in globals.css */",
    ),
    "utf8",
  );
  console.log(`@radix-ui/react-select ${name}: inline style element removed`);
}

// --- input-otp ---------------------------------------------------------------------------------
const OTP_GUARD = '!document.getElementById("input-otp-style")){';
const OTP_OFF = "!1/* StudyRoute: no inline <style> (CSP); the rules are in globals.css */){";

for (const name of ["index.mjs", "index.js"]) {
  const file = path.join(MODULES, "input-otp", "dist", name);
  if (!fs.existsSync(file)) continue;
  const source = fs.readFileSync(file, "utf8");
  if (source.includes(OTP_OFF)) continue;
  if (!source.includes(OTP_GUARD))
    throw new Error(`input-otp ${name} changed: update scripts/postinstall.mjs`);
  fs.writeFileSync(file, source.replace(OTP_GUARD, OTP_OFF), "utf8");
  console.log(`input-otp ${name}: inline style injection disabled`);
}
