# Enforcer Verdicts

`@dom-eval-enforcer` (`.github/agents/dom-eval-enforcer.md`) returns
one of three verdicts. Knowing the shape helps you parse the response
quickly.

## 1. "Ship it."

The eval that pins this behavior exists, the structure is correct, the
policy is satisfied. No action.

```
VERDICT: ship it

Behavior pinned by .github/evals/tools/test_get_skill_score.py.
Skill shape and memory architecture both pass.
```

## 2. "Add an eval / structure first."

Names the bucket, the file path, and the rule. Re-consult after the
file exists and the eval passes (or skips cleanly).

```
VERDICT: add an eval first

Bucket: tools
File:   .github/evals/tools/test_get_skill_score.py
Rule:   sb_get_skill_score must return a row from skill_scores for the
        current season; falling through to a 0.0 default is a silent
        fallback (see feedback_no_silent_fallbacks).

Once the file exists and `python .github/evals/run_all.py --only tools`
passes/skips cleanly, re-consult.
```

Or for a structural gap:

```
VERDICT: structure first

Missing: .github/skills/<new-skill>/references/*.md
Missing: .github/skills/<new-skill>/scripts/*.sh

test_skill_shape.py will fail until both exist.
```

## 3. "Don't ship."

The proposed change weakens an existing eval, removes a behavior
contract, breaks the skill shape, moves `docs/robots/MEMORY.md`,
or introduces a silent fallback. Ship-block.

```
VERDICT: don't ship

This diff relaxes test_skill_shape.py's exempt list to include
<skill-name>, but <skill-name> ships scripts/ and is not a pure
router. The right fix is to give it a reference, not exempt it.
```

## How to use a verdict

- **Ship it** → merge.
- **Add an eval first** → write the file, run it, re-consult.
- **Don't ship** → revert the change OR rework so the contract holds,
  then re-consult. Never override.
