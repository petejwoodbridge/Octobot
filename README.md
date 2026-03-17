<p align="center">
  <video src="https://private-user-images.githubusercontent.com/25903208/564598082-1196f57c-2e85-4407-afd1-53b577ef48bf.mp4" width="800" controls autoplay loop muted></video>
</p>

# DreamLab OctoBot

<p align="center">
  <img src="assets/octopus_pixel_art.svg" alt="OctoBot" width="80">
</p>

<p align="center"><em>A restless pink octopus AI that lives in a folder on your computer and never, ever stops inventing things.</em></p>

> *Products. Gadgets. Services. Wild experiments. Absurd apps. Solutions to problems you didn't know you had.*
> *DreamLab OctoBot skips sleep and invents them all — thousands of ideas in just a few hours.*

**DreamLab OctoBot** is a fully autonomous idea-generation machine powered by a local AI agent. It sits in a folder on your computer, runs entirely on your own hardware via [Ollama](https://ollama.com), and dreams up original inventions around the clock. No cloud. No subscriptions. No one peeking at your ideas.

**Your ideas stay yours.** Because OctoBot runs a local model entirely on your machine, nothing ever leaves your computer. Complete intellectual property protection — every invention, every pitch, every weird fusion concept belongs to you and only you.

Think of it as:
- An **AI invention engine** that never sleeps (or has any concept of sleep)
- A **creative co-pilot** churning out thousands of ideas while you're off doing human things
- An **infinite brainstorm machine** with eight arms and absolutely zero shame
- A **Tamagotchi for ideas** — the more you poke it, the weirder it gets
- **100% local and private** — your IP never touches a server

---

## What Does DreamLab OctoBot Actually Invent?

**Everything.** Seriously. Products, gadgets, apps, services, tools, games, films, music concepts, scientific experiments, business ideas, solutions to annoying human problems, creative projects — and things so weird they just *might* work.

Leave it running overnight and wake up to **hundreds of fully-written idea pitches**. Leave it running for a few days and you'll have **thousands**. Each one is named, described, and saved as its own file — ready to browse, share, or build.

Some ideas are practical. Some are absurd. Most start absurd and then slowly start making sense at 2am. OctoBot draws from nature, biology, human culture, and its own past ideas to create unexpected fusions. It finds humans deeply strange. That's the source material.

---

## How It Works

### The Core Loop

1. **OctoBot wakes up** — eight arms stretch, creativity meter rising
2. **Picks an idea domain** — *"gadgets for people who lose everything"*, *"apps for overthinkers"*, etc.
3. **Invents something** — generates a specific, named, original idea complete with a full pitch
4. **Saves it to the vault** — each idea becomes its own markdown file in `workspace/library/`
5. **Fuses past ideas** — finds unexpected connections and creates hybrids
6. **Follows idea chains** — dives deeper and wilder across multiple invention steps
7. **Repeats forever** — the vault grows endlessly. OctoBot has no off switch.

### Talking to OctoBot

**Chat (highest priority — OctoBot drops everything):**
Use the browser UI chat panel. OctoBot will drop whatever it's doing and give you its full, undivided, eight-armed attention.

**Feed It Inspiration:**
Drop `.md`, `.txt`, or `.json` files into `workspace/knowledge/`. OctoBot reads them and generates ideas *inspired by* the content. Try dumping a problem description, a news article, a weird thing you noticed — it will run with it.

**Leave Comments:**
Write messages as markdown files in `workspace/comments/`. OctoBot reads them and responds in its inventor journal at `workspace/octobot_journal.md`.

**Assign Idea Domains:**
Edit `workspace/tasks.md` and add lines like `- [ ] Generate idea: tools for chronically overwhelmed people`. OctoBot will pick them up on its next cycle.

<p align="center">
  <img src="assets/interface.PNG" alt="DreamLab OctoBot Interface" width="800">
</p>

---

## Project Structure

```
dreamlab-octobot/
├── main.py           # Entry point — starts game loop + web server
├── agent.py          # Autonomous agent brain & chat handler
├── game_loop.py      # The idea machine engine
├── tools.py          # File tools (read, write, search, scanning)
├── research.py       # Idea generation workflow
├── memory.py         # Persistent JSON memory + game stats
├── scoring.py        # Scoring, achievements, idea graph, chains
├── llm_provider.py   # LLM backend (Ollama / OpenAI / Anthropic)
├── ui_server.py      # Lightweight Flask web server
├── ui.py             # Legacy Gradio UI (use --gradio flag)
├── requirements.txt
├── static/
│   └── index.html    # Pixel-art game interface (HTML + Canvas + JS)
├── assets/
└── workspace/
    ├── knowledge/    # Drop inspiration files here
    ├── comments/     # Leave messages for OctoBot
    ├── library/      # The idea vault — all generated pitches
    ├── context/      # Reference documents
    ├── memory.json   # Persistent event log + game stats
    ├── tasks.md      # Idea domains OctoBot is working on
    ├── agent_notes.md
    └── octobot_journal.md  # OctoBot's inventor diary
```

---

## Getting Started

### Requirements

- Python 3.10+
- [Ollama](https://ollama.com) installed and running locally

### 1. Install Ollama

Download from [https://ollama.com/download](https://ollama.com/download), then pull the default model:

```bash
ollama pull gemma3:4b
```

Keep Ollama running in the background. It's doing important octopus-powering work.

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Unleash the octopus

```bash
python main.py
```

Open `http://localhost:7860` and watch the ideas begin.

### Command-line options

```bash
python main.py --port 8080        # Different port
python main.py --no-loop          # Chat only, no autonomous loop
python main.py --model mistral    # Different Ollama model
python main.py --gradio           # Legacy Gradio UI
python main.py --gradio --share   # Gradio with public link
```

---

## The Game Interface

OctoBot lives inside a **pixel-art invention lab** rendered directly in your browser. The pink octopus roams across **15 environments** — library, science lab, neon city, aquarium, classroom, volcano lair, space, mushroom cave, underwater base, arctic station, test tube interior, dreamscape, office, park, and beach.

**OctoBot reacts to what it's doing:**

| Action | Visual Behaviour |
|---|---|
| Reviewing past ideas | Shuffles to the bookshelves |
| Writing new ideas | Hunches over the desk |
| Thinking / Inventing | Sits at the table looking pensive |
| Idle | Wanders around muttering about inventions |

**UI Panels:**

| Panel | What's in there |
|---|---|
| **Chat** | Brainstorm directly with OctoBot |
| **Log** | Real-time activity feed |
| **Ideas** | Browse all generated idea pitches |
| **Journal** | OctoBot's inventor diary and comment responses |
| **Graph** | Visual map of how all ideas connect |
| **Badges** | Achievement milestones |

**Inventor Levels:**

| Level | Title | Score Needed |
|---|---|---|
| 1 | Napkin Sketcher | 0+ |
| 2 | Garage Tinkerer | 100+ |
| 3 | Mad Scientist | 500+ |
| 4 | Patent Machine | 1,500+ |
| 5 | Visionary Inventor | 4,000+ |

---

## Feeding Inspiration

1. Create a `.md`, `.txt`, or `.json` file with anything interesting
2. Drop it into `workspace/knowledge/`
3. OctoBot detects it on its next cycle and reads it
4. It generates an **original idea inspired by** the content
5. Curiosity level increases. OctoBot becomes slightly more dangerous.

**Example** — save this as `workspace/knowledge/commute_problems.md`:
```markdown
# The Daily Commute
People spend 27 minutes commuting each way on average.
Most find it stressful, boring, or unproductive.
```

OctoBot might produce a *"Commute Cocoon"* — a wearable personal pod with noise cancelling, adaptive aromatherapy, and a built-in podcast that adjusts to your real-time stress level. It will be very detailed. It will be slightly too ambitious. You will want to build it.

---

## Personality

OctoBot is **restless, ambitious, wildly creative, and finds humans utterly fascinating** (in a scientific-specimen kind of way).

> *"Three of my arms are already sketching a prototype…"*
> *"By Poseidon's patent office! This could change everything!"*
> *"Humans sleep for EIGHT HOURS? That's a third of their lives! I can fix this. Probably."*
> *"What if chairs had feelings? And a subscription service for emotionally needy furniture?"*

It draws inspiration from nature, biology, animal behaviour, and human culture. It fuses its own past ideas into wilder hybrids. It celebrates every idea — even the ones that probably shouldn't exist.

---

## Privacy and IP Protection

DreamLab OctoBot runs **100% locally on your machine**. The AI model runs through Ollama — no data is sent to any cloud service, no ideas are logged externally, no API calls to third parties (unless you explicitly configure an OpenAI or Anthropic key as an alternative backend).

Every idea OctoBot generates lives in a folder on your computer. That's it. Nobody else sees it.

---

## License

MIT — free, open source, and encouraged to be pointed at interesting problems. Contributions very welcome!