# Demo video tooling

Makes the silent footage of the demo video (`submission/VIDEO_SCRIPT.md`, 4:40, three people) from a **loopback sandbox**, plus a
guide video, captions and a cue sheet for the teammate who records the voice-over. Nothing is real: the data is synthetic, the
servers listen on 127.0.0.1 only, and the recorder refuses any other address.

```
python scripts/demo_video/make_video.py                   # about 10 minutes: record the ten scenes and build everything
python scripts/demo_video/make_video.py --dry             # rehearse: play every scene, screenshot every cue, no video
python scripts/demo_video/make_video.py --dry --only 4,5  # rehearse just some scenes (4 and later stage the bank's payment)
python scripts/demo_video/make_video.py --assemble-only   # build the videos again from the frames already recorded
python scripts/demo_video/assemble.py --timing            # when each sentence of each scene falls due (see "Re-recording")
```

Output goes to `dist/demo-video/` (git-ignored):

| File | What it is |
|---|---|
| `StudyRoute_Demo_Video_SILENT.mp4` | The picture, 1920 x 1080, constant 30 fps, exactly 4:40. The voice-over goes on this. |
| `StudyRoute_Demo_Video_GUIDE.mp4` | The same picture with the script's words under it, lighting up as they fall due. For the narrator to read along. |
| `StudyRoute_Demo_Video_captions.srt` | The script's words timed to the scenes (subtitles; adjust to the real voice). |
| `NARRATOR_CUE_SHEET.md` | Per scene: time, who is on screen, what happens when, the words and the pace, and how to record. |
| `timeline.json` | Where every scene and cue landed. |

`mix_voiceover.py` (needs only Python and ffmpeg) puts a recorded voice on the silent video and writes `StudyRoute_Demo_Video.mp4`.

## What you need

- `backend/.venv` (README, "Run it without Docker") and `cd web && npm ci && npm run build` (the recorder serves `web/out` with the real
  content-security policy, so the video shows the same pages a visitor gets).
- Node 20 or later, Google Chrome (set `CHROME_PATH` if it is not in the usual place), and ffmpeg 5.1 or later with libx264, freetype and
  libass (`--ffmpeg PATH` or `FFMPEG=...`; `pip install imageio-ffmpeg` also works).
- Free ports 8120 and 8190 (`--api-port`, `--web-port`).

## How it works

1. `script_scenes.py` reads the tables in `submission/VIDEO_SCRIPT.md`: when each scene starts, how long it runs, who is on screen and
   the words. The video can therefore never drift from the script, and scenes keep the script's numbers (0 to 9).
2. `make_video.py` makes a new database, starts the API and the UI (without any cloud-model key), and runs `record.mjs`.
3. `record.mjs` signs in as the parent, the bank reviewer and the student in three browser sessions, and plays the "What to do" column
   at human speed: a drawn pointer, click ripples, highlights on what the narrator is describing. Each scene is paced to the sentence
   being said: `at(t)` waits until t seconds into the scene, and t is where the narrator reaches the sentence that describes what happens
   next. The bank's payment is staged between scenes 3 and 4 with `python -m app.scripts.review_demo --leave-open`. Chrome's screencast
   saves the frames and when each was painted.
4. `assemble.py` cuts each scene to the length the script gives it (a scene that ran long is sped up a little, a short one holds its
   last picture), adds the bar under the picture (who is on screen, the sandbox label), a dip to black where the window changes, and writes
   the videos, captions and cue sheet.

Off camera, before scene 0, the parent says "hello" to the assistant once. The chat header reads "Cloud assistant" until the first
reply (a placeholder, not what this sandbox runs); with the greeting answered, the header is right when the chat opens on camera.

The pointer, ripples and highlights are drawn with the DOM and CSSOM only, so the application's strict content-security policy stays on.
The accounts, the password and the sandbox MFA code are read from the sandbox's own `/api/v1/health`; nothing is hard-coded.

## Re-recording

A take is repeatable: the pointer's drift is seeded and the data is new each time. Run `--dry` first after changing the script or the UI.
It prints any cue that ran late (`late:`), any step that had to scroll its target into view (`scrolled:`, which can hold a step up) and
a failure with its screenshot (`frames/fail_sN.png`), and it saves a screenshot at every cue to `dist/demo-video/frames/dry/`. A rehearsal
is slower than a take because of those screenshots. If the staged quote would expire (five minutes) the recorder stops and says so.

If you change the words of the script, re-time the `at()` cues in `record.mjs`: `assemble.py --timing` prints when each sentence falls due.

## Limits

- The footage is silent on purpose: the narration is a person's voice. The captions are timed from the script, not from the voice.
- Scenes 0 and 9 are a little quick (about 145 words a minute). The cue sheet marks them.
- The assistant's wording comes from the local trained models (no cloud key is ever passed to the recorder).
- Scene 7 shows the student's view of a payment that has already settled, so the "Only the paying parent can approve" sentence of an open
  payment is not on screen there; the Actions card ("This payment is finished") and the missing approve button carry the point.
