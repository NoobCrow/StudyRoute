# Quick language + top settings patch

Apply AFTER StudyRoute-saved-api-key-update.zip. Stop backend and frontend, then merge the
contents of this StudyRoute folder into your existing project. Keep .env, .venv, backend/data
and node_modules. Restart both servers. No HF Space upload, new dependency or database reset.

AI connection settings now sits below the assistant header, outside the message scroll area.
Normal saved settings are collapsed. The expanded controls have a bounded scroll height.
Saved API-key persistence is unchanged.

Each model request now explicitly selects the response language from the current message,
not previous conversation or Bengali terminology hints. English is the default for non-Bengali
non-recognized-Banglish text; Bengali script selects Bengali, common Banglish selects Latin-script
Banglish. Explicit 'Reply in English/Bengali' preference is supported. Bengali terminology hints
are restricted to Bengali replies. This is a prompt-language fix, not a universal language detector
or output-language guarantee for every model.

Verification: 53 backend language/quality/LLM-mode tests passed; Next assistant tests and typecheck
passed. Provider HTTP mocked; no live Gemini response or full build/browser retest for this quick patch.
