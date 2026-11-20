# Real-time game vision

The [real-time engine plan](REALTIME_ENGINE_PLAN.md) scopes a local development
demo for the confirmed game direction. The [README](../README.md) describes the
runnable paths. The turn-based prototype and its evaluation infrastructure remain
the reproducible baseline. Any paid invocation requires separate approval.

## Intended experience

Parallax Relay is intended to become a real-time cooperative platformer,
adventure, and puzzle game. The three AI-controlled robots SPECTRA, PYRA, and
FLUX explore spaces, use their distinct capabilities and observations, and
cooperate to overcome obstacles.
The world should have real physics: robots can move and jump, and jumping,
landing, collisions, and environmental interactions matter to navigation and
puzzle solving. The engine plan specifies trial physics rules for one development
room.

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
followed by real-time action. Every accepted command sequence in a window starts
on the same authoritative simulation tick. Replies can arrive at different wall
times. After the host closes admission and resolves every role's slot, it installs
the accepted programs and any neutral fallbacks together on the next simulation
tick. Until then, submitted controls stay sealed.

Whether physics freezes during discussion remains a playtest choice. The trial
modes freeze physics or continue neutral physics with gravity and collisions.
Both use one frozen sample per role for the window and one shared start tick.
Evaluate how each mode affects the rhythm when model replies arrive at different
times.

## Baseline and boundaries

The turn-based Python engine resolves discrete turns after phased communication and
sealed commitments. Its nine curated rooms, role-specific PNG/HUD observations,
offline fixtures, recordings, controls, and campaign infrastructure support the
turn-based prototype and its evaluation. Scripted fixtures verify host behavior.
The bounded live smoke measured provider request completion on a single baseline
turn. Full-game model cooperation remains unevaluated.

Preserve the current prototype and its historical evidence as a reproducible
baseline while exploring the new game. The present player contract uses each
role's own observation image and HUD; changing that interface needs a separate
design decision. The simulation remains authoritative over actions and outcomes;
model text and images are untrusted data. Role-local histories, notes, objectives,
and observations stay private except for information deliberately made public.
Full world state and complete recordings remain spectator-only. Any new rendering,
communication, or replay design must account for these boundaries.

## Proposed next-stage exploration

The engine plan scopes the first development demo. These exploration areas also
cover future rooms, presentation, and evaluation.

1. Define a small playable space and demonstrate movement, jumping, landing,
   collision, and a cooperative physical puzzle with offline controls. Establish
   observable success and failure cases for physics and interaction.
2. Explore how model decisions connect to movement and communication, including
   responsiveness under delayed, missing, invalid, or stale replies. Compare clock
   modes and action budgets while preserving the shared start tick.
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

- Which discussion clock mode best serves fairness, responsiveness, and the
  experience of real-time play?
- Which window lengths, action budgets, and timeouts work across measured model
  delays and development scenarios?
- Which trial physics and interaction rules should carry over to future rooms?
- How do bubbles and eventual speech represent public messages, handle timing and
  accessibility, and avoid exposing private information? What recordings are needed?
- How should real-time experiments be evaluated and compared while preserving the
  existing turn-based controls and the development/held-out distinction?

The engine plan selects trial implementation settings. Voice production, measured
real-time provider latency, and a release date remain open.
