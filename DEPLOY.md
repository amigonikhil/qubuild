# Putting QuBuild online — the whole thing, explained

You are going to take the folder on your laptop, put a copy of it on the
internet, and get back a link anybody can open.

Nothing here needs you to understand servers. It is: upload the files, tell
the host which file to start, paste two settings, done. Budget **45 minutes**
the first time, most of which is waiting.

---

## What "deploying" actually means

Right now QuBuild only exists on your laptop. When you run
`Start-QuBuild.bat`, your own machine does two jobs at once:

- it **runs** QuBuild, and
- it **shows** QuBuild to you in a browser.

Nobody else can open it, because nobody else can reach your laptop.

Deploying means handing a copy of the folder to a company that owns computers
sitting in data centres. One of their computers does the running, your laptop
does nothing, and anyone in the world with the link does the looking.

You are renting the *running*, not the *thinking*. QuBuild still does all its
quantum simulation wherever it happens to be — on a laptop, or on their
machine. That is why "no cloud account needed" is still true after you deploy:
the host is a convenience so people can click a link, not a requirement for
the app to work. Keep that distinction ready; a judge may test it.

---

## The four things you will do

| Stage | What | How long |
|---|---|---|
| 1 | Put the code on GitHub | 15 min |
| 2 | Create a free database | 10 min |
| 3 | Deploy on Streamlit | 10 min + build wait |
| 4 | Paste your settings and check | 5 min |

Plus one thing before any of it.

---

# Stage 0 — Revoke the old key. Do this now.

Your OpenAI key used to sit in plain text in `app.py`. I removed it from the
deploy copy, but the key itself is still alive at OpenAI until you kill it.
Anyone who ever saw that file can spend your money with it.

1. Go to **platform.openai.com**
2. Sign in → **API keys** in the left menu
3. Find the one beginning `sk-proj-`
4. Click the bin icon → **Revoke**

Do this even if you decide not to deploy at all.

---

# Stage 1 — Put the code on GitHub

## Why GitHub

The hosting company needs to read your files. You can't hand them a USB stick,
so you put the files somewhere public on the internet and give them the
address. GitHub is where code lives. It is free and the host reads directly
from it.

A side benefit: when you change something later, you update GitHub and the
live site updates itself. No re-uploading.

## 1.1 Turn on hidden files first — do not skip this

Two of the folders you must upload start with a dot: **`.streamlit`** and
**`.gitignore`**. Windows hides anything starting with a dot, so right now you
probably cannot see them and will upload without them.

What breaks if you miss them:

- no `.streamlit` → the site loads in Streamlit's default white theme instead
  of your dark one, and the Deploy button shows to visitors
- no `.gitignore` → nothing protects you from accidentally uploading your
  database file, which holds password hashes

**In File Explorer:** open the deploy folder → **View** tab at the top →
tick **Hidden items**. `.streamlit` and `.gitignore` appear.

## 1.2 Make an account

Go to **github.com** → **Sign up**. Username, email, password, verify the
email. Free.

## 1.3 Make a repository

A repository — "repo" — is one project's folder on GitHub.

1. Go to **github.com/new**
2. **Repository name:** `qubuild`
3. **Description:** optional, e.g. "Interactive quantum computing learning platform — SIH 2026"
4. Choose **Public**

   It has to be public for free Streamlit hosting to read it. This is your own
   work and a hackathon submission, so that is fine — but it is why Stage 0
   matters. Once it is public, it is public.

5. **Do not tick** "Add a README file". Your folder already has one; ticking it
   creates a conflict.
6. **Create repository**

## 1.4 Upload the files

You land on a page saying the repo is empty. Find the link
**"uploading an existing file"** in the middle of the page and click it.

Then:

1. Open the deploy folder in File Explorer in another window
2. Select **everything inside it** — `Ctrl+A`
3. Drag it all onto the GitHub upload area

   Drag the **contents**, not the folder itself. If you drag the folder, every
   path gets an extra level and Streamlit will not find `app.py`.

4. Wait for the file list to finish appearing
5. In the "Commit changes" box type `QuBuild`
6. **Commit changes**

## 1.5 Check what actually arrived

Look at your repo's file list. You should see:

```
.streamlit/
qubuild/
tests/
.gitignore
DEPLOY.md
README.md
Start-QuBuild.bat
app.py
requirements.txt
run_tests.py
```

**Three things to verify:**

- **`app.py` is in the list at the top level**, not inside another folder. If
  everything is nested inside a `deploy2` or similar folder, delete the repo
  and upload again, dragging the contents.
- **`.streamlit` is there.** If not, you missed step 1.1. Go back, turn on
  hidden items, and upload that folder on its own with "Add file → Upload
  files".
- **`qubuild.db` is NOT there.** If it is, click it → bin icon → commit. It
  holds password hashes and should never be public.

## If you prefer the command line

Same result, faster, if you already have git:

```
cd path\to\deploy-folder
git init
git add .
git commit -m "QuBuild"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/qubuild.git
git push -u origin main
```

`.gitignore` is respected automatically, so the database cannot slip in.

---

# Stage 2 — A database that does not disappear

## Why you need this

The host puts QuBuild on a computer. If nobody opens your link for a while,
they take that computer back and give it to someone else. Next visitor, fresh
computer, and QuBuild starts from nothing.

QuBuild keeps accounts, classes, classroom codes, progress and notifications
in one file called `qubuild.db`, sitting on that computer. Take the computer
away, the file goes too.

**In practice:** your student signs up Monday with your classroom code.
Tuesday nobody opens the link. Wednesday she comes back and her account does
not exist. Not a wrong password — gone. Your class, gone. Everyone signs up
again.

A database service fixes it. It is a separate company whose only job is
storing data and never losing it. QuBuild writes there instead of to the local
file, so when it wakes up on a new computer, everything is still there.

Skip this only if the link is purely for the jury to glance at and nobody will
build up anything worth keeping.

## 2.1 Create it

**supabase.com** — free, no card.

1. **Start your project** → sign in with GitHub (one less password)
2. **New project**
3. **Name:** `qubuild`
4. **Database Password:** click Generate, then **copy it somewhere safe now**.
   You need it in two minutes and it is not shown again.
5. **Region:** pick the closest — for India, Mumbai / `ap-south-1`
6. **Create new project**

It takes one to two minutes to build. Wait for it.

## 2.2 Get the connection string

The connection string is one line that tells QuBuild where the database is and
how to open it. Like a postal address with the key written on it. You never
type it yourself — Supabase writes it for you.

1. In your project, click **Connect** (top bar), or
   **Project Settings → Database**
2. Find **Connection string**
3. Choose the **URI** tab
4. Copy the whole line

It looks like this:

```
postgresql://postgres.abcdefghijkl:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
```

Reading it left to right:

| Piece | Meaning |
|---|---|
| `postgresql://` | what kind of database |
| `postgres.abcdefghijkl` | the username |
| `[YOUR-PASSWORD]` | **you replace this** with the password from 2.1 |
| `aws-0-ap-south-1.pooler.supabase.com` | which machine, where |
| `5432` | which door on that machine |
| `postgres` | which database on it |

**Replace `[YOUR-PASSWORD]`** — square brackets and all — with your real
password. Paste the finished line into Notepad for a moment; you need it in
Stage 4.

If your password contains `@`, `/`, `:` or `#`, generate a new one without
them. Those characters have meaning inside the line and will break it.

## 2.3 One edit to make now

QuBuild needs one extra piece of software to speak to PostgreSQL, and it is
switched off by default because a laptop does not need it.

In your GitHub repo:

1. Click **requirements.txt**
2. Click the **pencil** icon to edit
3. Find the last line:

   ```
   # psycopg[binary]>=3.1
   ```

4. Delete the `# ` so it reads:

   ```
   psycopg[binary]>=3.1
   ```

5. **Commit changes**

Miss this and the app starts, silently fails to reach the database, and falls
back to the file that disappears. It looks like it is working right up until
it is not.

---

# Stage 3 — Deploy

## 3.1 Sign in

Go to **share.streamlit.io** → **Continue with GitHub** → **Authorize**.

You are giving Streamlit permission to read your repos. That is the whole
point — it needs to read your code to run it.

## 3.2 Create the app

1. **Create app**
2. Choose **Deploy a public app from GitHub**
3. Fill in:
   - **Repository:** `your-username/qubuild`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL:** pick the address, e.g. `qubuild` →
     `qubuild.streamlit.app`. Taken names are rejected; try `qubuild-innovatrix`.
4. If there is an **Advanced settings** link, open it and set **Python
   version 3.11**. It is the best-tested version for these quantum libraries.
5. **Deploy**

## 3.3 Wait, and watch the log

A page opens with text scrolling past. That is the host installing everything
QuBuild needs — four quantum SDKs among them, about 500 MB.

**Expect 5 to 10 minutes.** It is not stuck.

You will see lines like `Collecting qiskit`, `Installing collected
packages...`, then finally `You can now view your Streamlit app`.

When it finishes, QuBuild appears. **It works now** — but every account made
on it will vanish, until you finish Stage 4.

---

# Stage 4 — Tell it about the database

## 4.1 Open the Secrets box

Secrets are settings you give the app privately. They are not in your GitHub
repo and no visitor can see them. That is why the database password goes here
and not in the code.

1. On your running app, bottom-right **⋮** → **Settings**

   (Or from **share.streamlit.io**, the **⋮** beside your app → **Settings**.)

2. Click **Secrets**

## 4.2 Paste

Into the empty box, paste this — with your real line from Stage 2.2:

```toml
QUBUILD_DB_URL = "postgresql://postgres.abcdefghijkl:your-real-password@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
```

Keep the double quotes. Keep the name exactly as written — capitals and
underscores both matter.

**Save.** The app restarts by itself, thirty seconds or so.

## 4.3 Optional: give the tutor a language model

The tutor already works with no key at all — 23 built-in articles plus a
rule-based analyser that reads the student's own circuit. Add a model only if
you want it to answer open-ended questions too.

Add two more lines to the same Secrets box:

```toml
QUBUILD_PROVIDER = "groq"
QUBUILD_API_KEY  = "your-key-from-console.groq.com"
```

Groq and Gemini both have free tiers. The key lives only in this box — never
in your code, never on GitHub.

---

# Stage 5 — Check it properly

Open your link and walk through this. It takes two minutes and catches
everything that usually goes wrong.

**Does it load?**
The QuBuild sign-in screen, dark theme. White background means `.streamlit`
did not upload.

**Do the three roles appear?**
**Create account** → you should see Learner, Student, Instructor.

**Does a class work?**
Sign up as Instructor, class name `TEST-1A`. Go to Instructor view and read
the classroom code. Sign out, sign up as Student with that code. You should
land in the class. Sign back in as the instructor — the student is on the
roster.

**Is the database the right one?**
Go to **Deliverables**. It names the storage in use. It must say
**postgresql**. If it says sqlite, Stage 4 did not take — check the secret
name is spelled exactly `QUBUILD_DB_URL` and that you uncommented `psycopg`.

**Do all four SDKs work?**
Circuit Studio → run a circuit → look at **CROSS-SDK CHECK**. It should list
four rows: QuBuild, Qiskit Aer, Cirq, PennyLane. Fewer means one failed to
install — check the build log.

**The real test.**
Close the tab. Come back tomorrow. Sign in with the same username. Still
there? Done.

---

# When something breaks

**"Error installing requirements" / build fails**

The four SDKs are heavy. Edit `requirements.txt` on GitHub, put `#` back in
front of `cirq-core` and `pennylane`, commit. The app redeploys itself.

It will still run — but the cross-SDK check drops from four libraries to two,
and that check is the thing nobody else does. Try the full set first; only
trim if it genuinely will not build.

**App boots, then a red error appears**

Click **Manage app** at the bottom right to read the log. The last few lines
name the actual problem, usually a missing package. Send me that text.

**Deliverables says sqlite, not postgresql**

One of three things:

- `psycopg[binary]>=3.1` still has a `#` in front of it in `requirements.txt`
- the secret is misspelled — it must be exactly `QUBUILD_DB_URL`
- `[YOUR-PASSWORD]` is still literally in the connection string

**Database connection refused**

Supabase offers more than one connection string, on different ports. Go back
to **Connect**, copy the other one they show, and paste that instead.

**Everything is very slow**

Normal for a free tier. The machine is small and shared. Present from your
laptop, use the link for sharing.

**"This app has gone to sleep"**

Also normal. Whoever clicks **Wake it up** waits about 30 seconds. With the
database attached, nothing is lost — that is exactly what Stage 2 bought you.

---

# What it costs

Nothing. GitHub public repos: free. Streamlit Community Cloud: free.
Supabase free tier: 500 MB of database, far more than a few hundred students
need.

No card anywhere.

---

# For the jury

**Demo from your laptop.** It is faster, it cannot be broken by venue wifi,
and it lets you make the strongest move available to you: pull the network
cable mid-demo and keep going. A cold-starting free host cannot do that.

**Put the link on your last slide** so they can open it themselves afterwards.

**If they ask whether you need the cloud:** the honest answer is no, and the
deployment does not weaken it. Hosting the website is a convenience for
sharing a link. The simulation runs wherever the app runs — including a
college laptop with no account at all, which is the whole argument.
