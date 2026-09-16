# `src/auth/` — The door

**Plain job:** decide who is allowed into the building. It has no opinion about what
happens inside.

This folder is completely separate from the medical pipeline. It does not import the
grader, the quality gate, the lesion detector or the rule engine, and none of them import
it. You could delete the whole folder and the screening science would still run.

## The files

| File | Plain job |
|---|---|
| `config.py` | Reads the settings, and refuses to start if they are dangerous |
| `models.py` | What an account is; tidying up phone numbers |
| `otp.py` | Makes the one-time code, checks it, and stops people guessing |
| `sms.py` | Sends the code. Swappable — no SMS company is named anywhere else |
| `security.py` | Sign-in tickets, and the guards on each door |
| `service.py` | The actual actions: send a code, check it, sign out, approve a doctor |
| `storage.py` | Remembers accounts. In its own files, never mixed with scans |
| `routes.py` | The web addresses: `/v1/auth/...` |

## No passwords

There is no password box, and no place to put one. You prove who you are by showing that
you hold the phone number: the system sends a six-digit code and you type it back.

## Choosing "Doctor" does not make you a doctor

Anyone can tick "Doctor Account" at signup. What that does is create an account marked
**not verified** and file a request. Only two things can mark an account verified — an
administrator using the admin address, or someone with access to the server running
`scripts/approve_doctor.py`. Neither is reachable by filling in a form.

Until then the person can sign in and screen images, but the reports area says
**"Doctor verification pending."**

## The role is never taken from the browser

The sign-in ticket says *which account you are*, not *what you are allowed to do*. Every
time you knock on a protected door, the server looks your account up and reads your role
off its own records. Editing anything in the browser changes what you see drawn on the
screen; it changes nothing about what the server will hand over.

## The code on the screen

When running locally the one-time code is printed on screen instead of sent by SMS,
because there is no SMS account. That shortcut is **impossible to leave switched on** in a
real deployment: the service refuses to start if you try. See `docs/AUTH.md`.
