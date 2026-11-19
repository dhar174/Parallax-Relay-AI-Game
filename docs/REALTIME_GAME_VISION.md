# Real-time game vision

**Status: confirmed game direction; implementation to be designed.** This plan
describes the intended game and next-stage exploration. It does not describe
implemented mechanics, choose an engine or provider, or authorize live spending.
The existing turn-based prototype and its evaluation infrastructure remain the
current, usable baseline; see the
[README](../README.md), [architecture](ARCHITECTURE.md), and [roadmap](../ROADMAP.md).

## Intended experience

Parallax Relay is intended to become a real-time cooperative platformer,
adventure, and puzzle game. The three AI-controlled robots SPECTRA, PYRA, and
FLUX explore spaces, use their distinct capabilities and observations, and
cooperate to overcome obstacles.
The world should have real physics: robots can move and jump, and jumping,
landing, collisions, and environmental interactions matter to navigation and
puzzle solving. The specific physics rules and implementation remain to be designed.

Preserve the approved light visual direction and the three recognizable little
robot characters as the basis for future graphics. The artwork still needs touch-ups;
develop jump and landing frames from those designs without treating frames as final.
Future spectator graphics must not overwrite the current model-facing sensor images.

The spectator goal is to follow a live running game, with public dialogue bubbles
above the robots' heads showing their coordination. Eventual text-to-speech is
intended to give those messages voices. Bubble behavior, accessibility, presentation, voice
selection, and any speech provider are open design work. Public speech must not
turn private objectives, notes, or role-specific observations into shared data
unless a role actually discloses them.

The desired rhythm is fairly quick play, with brief thinking and discussion pauses
followed by real-time action. Whether the simulation pauses during those intervals
or coordination waits for all robots remains open. Model requests take time, so
the game must account for decision latency. That constraint does not itself decide
whether the game is turn-based or whether the world runs or pauses while a model
is thinking. The intended destination remains
a real-time experience; its relationship to model decision timing needs deliberate
design and testing.

## Baseline and boundaries

Today the Python engine resolves discrete turns after phased communication and
sealed commitments. Its nine curated rooms, role-specific PNG/HUD observations,
offline fixtures, recordings, controls, and campaign infrastructure support the
existing prototype and its evaluation. They do not implement platformer physics,
real-time movement, discussion bubbles, or speech. Scripted successes and the
bounded live smoke are not evidence of full-game model cooperation.

Preserve the current prototype and its historical evidence as a reproducible
baseline while exploring the new game. The present player contract uses each
role's own observation image and HUD; changing that interface needs a separate
design decision. The simulation remains authoritative over actions and outcomes;
model text and images are untrusted data. Role-local histories, notes, objectives,
and observations stay private except for information deliberately made public.
Full world state and complete recordings remain spectator-only. Any new rendering,
communication, or replay design must account for these boundaries.

## Proposed next-stage exploration

These are areas for separately scoped designs and prototypes, not delivered
milestones or a committed order:

1. Define a small playable space and demonstrate movement, jumping, landing,
   collision, and a cooperative physical puzzle with offline controls. Establish
   observable success and failure cases for physics and interaction.
2. Explore how model decisions connect to movement and communication, including
   responsiveness under delayed, missing, invalid, or stale replies. Compare timing
   options before selecting a coordination contract.
3. Design role-specific observations and public communication for the new world,
   preserving the current image-based interface until a separate decision changes
   it. If model-facing sensor images change later, compare old and new versions in
   development rooms before freezing a new evaluation build; keep all six held-out
   rooms out of tuning. Prototype bubbles and later evaluate speech presentation
   and accessibility.
4. Design recording, replay, provenance, and evaluation appropriate to the chosen
   simulation and timing model. Preserve existing records and distinguish new
   results from the turn-based baseline. Explore a live spectator stream of the
   actual running simulation, with its public dialogue and privacy boundaries.
5. Validate offline first, using development rooms or separately designated
   development scenarios for tuning; exclude held-out rooms from design tuning.
   The existing registered confirmation protocol applies to the turn-based
   prototype. A future real-time environment needs its own separately designed
   and registered evaluation. Paid model runs require separate explicit
   authorization, selected models, credentials, and bounded limits.

## Decisions still open

- Does the simulation continue, pause, or use another approach while a model
  request is pending? How does the choice affect fairness, responsiveness, and
  the experience of real-time play?
- When are observations sampled and decisions requested? How are different
  response times, synchronization, retries, timeouts, and stale replies handled?
- How long does a selected action persist, and what happens when a robot has no
  fresh action? How do simultaneous actions and physical interactions resolve?
- What are the physics rules, world representation, rendering technology, and
  execution architecture? Which parts of the existing engine can be reused?
- How do bubbles and eventual speech represent public messages, handle timing and
  accessibility, and avoid exposing private information? What recordings are needed?
- How should real-time experiments be evaluated and compared while preserving the
  existing turn-based controls and the development/held-out distinction?

These questions need design and evidence; no specific game engine, voice service,
provider latency, or release date is selected here.
