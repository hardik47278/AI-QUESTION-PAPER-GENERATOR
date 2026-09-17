# EVALVIA AI — Smart Question Paper Generator

## 1. Problem

The system generates question papers from teacher requirements such as:

```text
Total Marks: 40

Difficulty:
Easy: 30%
Medium: 50%
Hard: 20%

Topics:
Algebra: 40%
Geometry: 30%
Trigonometry: 30%

Question Type:
MCQ: 40%
Short Answer: 40%
Long Answer: 20%
```

The challenge is not simply generating questions.

The system has to answer:

1. Can the requested paper actually be constructed from the available question bank?
2. What happens if some constraints cannot be satisfied simultaneously?
3. Does the paper feel like a real examination paper instead of random question selection?
4. Can one question be regenerated without rebuilding the entire paper?
5. Should the decision be made by an LLM, deterministic logic, or both?
6. What happens when the constraints themselves conflict?

The core architecture is therefore:

```text
LLM
+
Deterministic Logic
+
Question Intelligence
+
State-aware LangGraph
+
Targeted Repair
+
Human-in-the-loop
```

---

# 2. Core Design Principle

The central principle is:

> **Generation should be flexible, but validation should be strict.**

The LLM is useful for:

```text
Understanding teacher requirements
Qualitative evaluation
Semantic similarity
Question clarity
Difficulty consistency
Paper coherence
```

Deterministic logic handles:

```text
Total marks
Question count
Percentage calculations
Topic marks
Difficulty marks
Question-type marks
Duplicate IDs
Schema validation
```

Question Intelligence handles:

```text
What questions actually exist?
What combinations are available?
Which requested combinations are impossible?
```

LangGraph state handles:

```text
Current paper
Previous evaluation
Failed constraints
Affected questions
Repair information
Routing decisions
```

---

# 3. Architecture

```text
                  TEACHER REQUIREMENTS
                           │
                           ▼
                  ┌─────────────────┐
                  │ BLUEPRINT AGENT │
                  │      LLM        │
                  └────────┬────────┘
                           │
                           ▼
             ┌──────────────────────────┐
             │ QUESTION INTELLIGENCE    │
             │                          │
             │ Validation               │
             │ Normalization            │
             │ Inventory                │
             │ Feasibility information  │
             │ Conflict analysis        │
             └────────────┬─────────────┘
                          │
                          ▼
             ┌──────────────────────────┐
             │ PAPER GENERATION AGENT   │
             │                          │
             │ Candidate construction   │
             │ Constraint-aware         │
             │ Targeted repair          │
             │ Cost-based replacement   │
             └────────────┬─────────────┘
                          │
                          ▼
             ┌──────────────────────────┐
             │ EVALUATION AGENT         │
             │                          │
             │ Deterministic checks     │
             │ +                        │
             │ LLM quality checks       │
             └────────────┬─────────────┘
                          │
                          ▼
                    ┌───────────┐
                    │  ROUTER   │
                    └─────┬─────┘
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
        PASS            REPAIR          UNCERTAIN
          │               │                │
          │               ▼                ▼
          │        Targeted repair      HUMAN REVIEW
          │               │
          │               ▼
          │          EVALUATION
          │
          ▼
      FINAL PAPER
```

---

# 4. State-Aware Architecture

The system uses a state-aware LangGraph workflow.

The state conceptually contains:

```text
Blueprint
Question Bank
Current Paper
Selected Question IDs
Evaluation Result
Constraint Failures
Affected Question IDs
Candidate Information
Repair Information
Confidence
Routing Decision
```

This matters because the system does not treat every repair as a new paper-generation request.

For example:

```text
Current Paper

Q1 ✓
Q2 ✓
Q3 ✗
Q4 ✓
Q5 ✓
Q6 ✓
Q7 ✓
Q8 ✓
```

The evaluator can record:

```text
affected_question_ids = ["Q3"]
```

The generator then knows:

```text
Keep Q1
Keep Q2
Replace Q3
Keep Q4
Keep Q5
Keep Q6
Keep Q7
Keep Q8
```

This gives the architecture an important property:

> **Change locally, validate globally.**

---

# 5. Question Intelligence — Understanding What Is Actually Possible

Before generation, the Question Intelligence Agent analyzes the question bank.

It builds inventories such as:

```text
Topic
Difficulty
Question Type
Topic × Difficulty × Question Type
Marks
```

For example:

```text
Algebra
 ├── Easy
 │    ├── MCQ: 8
 │    └── Short: 3
 │
 ├── Medium
 │    ├── MCQ: 5
 │    └── Short: 7
 │
 └── Hard
      └── Long: 4
```

This is important because a simple topic inventory is not enough.

Suppose the teacher requests:

```text
Algebra + Hard + MCQ
```

The question bank may contain:

```text
Algebra = many
Hard = many
MCQ = many
```

but:

```text
Algebra × Hard × MCQ = 0
```

Therefore the individual categories existing independently does **not** mean their combination is available.

The multidimensional inventory exposes this.

---

# 6. The Interesting Problem — Constraints Can Conflict

Suppose the teacher requests:

```text
40-mark paper

Algebra: 50%
Geometry: 50%

Easy: 25%
Medium: 50%
Hard: 25%

MCQ: 50%
Short: 25%
Long: 25%
```

Now imagine the available question bank has very limited combinations.

For example:

```text
Hard Algebra MCQ = 0
Hard Geometry MCQ = 8
```

The system cannot simply say:

```text
"Hard MCQ exists, so everything is fine."
```

because the actual intersection:

```text
Hard + Algebra + MCQ
```

may be unavailable.

This is why the system analyzes constraints as **combinations**, not only as independent percentages.

---

# 7. Conflict Subset — Do Not Treat the Whole Request as Impossible

This is an important idea in the architecture.

When constraints cannot all be satisfied, the system should identify the **small subset of constraints causing the problem**.

For example, suppose the teacher requests:

```text
Algebra = 50%
Hard = 25%
MCQ = 50%
```

but the bank has no:

```text
Hard + Algebra + MCQ
```

The problem may not be:

```text
"Algebra is impossible."
```

or:

```text
"Hard is impossible."
```

or:

```text
"MCQ is impossible."
```

Individually, all three may exist.

The conflict is their combination:

```text
Algebra
+
Hard
+
MCQ
```

So the system records the more precise conflict:

```text
Conflict subset:

{topic = Algebra,
 difficulty = Hard,
 question_type = MCQ}
```

This is much more useful than simply returning:

```text
Generation failed.
```

---

# 8. Why Finding a Conflict Subset Matters

Suppose the request is:

```text
40 marks
8 questions
50% Algebra
50% Geometry
25% Easy
50% Medium
25% Hard
50% MCQ
25% Short
25% Long
```

There may be many constraints.

If something fails, we do not want to conclude:

```text
All constraints are impossible.
```

Instead we want to answer:

> **Which combination of requirements is actually causing the infeasibility?**

For example:

```text
Conflict:

Algebra + Hard + MCQ
```

while:

```text
Algebra + Medium + MCQ     ✓
Geometry + Hard + MCQ      ✓
Algebra + Hard + Long      ✓
```

This means the system has identified a **localized conflict**.

That allows a much more graceful response.

---

# 9. Conflict Analysis as Constraint Diagnostics

Conceptually, each requirement can be represented as a constraint:

```text
C1 = total marks = 40

C2 = Algebra = 20 marks

C3 = Geometry = 20 marks

C4 = Hard = 10 marks

C5 = Medium = 20 marks

C6 = Easy = 10 marks

C7 = MCQ = 20 marks

C8 = Short = 10 marks

C9 = Long = 10 marks
```

The question bank provides the feasible combinations.

The system then reasons about whether the requested combination can be constructed.

If the complete set:

```text
{C1,C2,C3,C4,C5,C6,C7,C8,C9}
```

cannot be satisfied, the useful question becomes:

> Which smaller subset of constraints is responsible?

For example:

```text
{C2, C4, C7}
```

might correspond to:

```text
Algebra
+
Hard
+
MCQ
```

being unavailable.

This is more actionable than reporting every constraint as failed.

---

# 10. Conflict Detection Should Be Transparent

The system should report something like:

```text
Constraint conflict detected.

Requested:
20% Hard Algebra MCQ

Question bank:
No Hard Algebra MCQ questions available.

Related combinations available:
Hard Geometry MCQ
Medium Algebra MCQ
Hard Algebra Long

The conflict is therefore localized to:
Topic + Difficulty + Question Type
```

This gives the teacher information about what is actually wrong.

The system does not silently change:

```text
Algebra → Geometry
```

or:

```text
Hard → Medium
```

without telling the teacher.

---

# 11. What Happens After Finding the Conflict?

Once the conflicting subset is identified, the system attempts controlled repair.

Possible strategies are:

```text
Keep topic, relax difficulty
```

or:

```text
Keep difficulty, change question type
```

or:

```text
Keep topic and type, adjust distribution
```

or:

```text
Ask teacher for a decision
```

The system should not make a hidden relaxation.

Instead:

```text
Conflict
   ↓
Identify conflicting constraints
   ↓
Determine feasible alternatives
   ↓
Calculate impact
   ↓
Attempt repair if policy allows
   ↓
Otherwise ask human
```

---

# 12. Why This Is Better Than Simply Failing

Without conflict analysis:

```text
No exact match
      ↓
Generation failed
```

This is technically safe but not very useful.

With conflict analysis:

```text
No exact match
      ↓
Find conflicting subset
      ↓
Explain exact conflict
      ↓
Find feasible alternatives
      ↓
Estimate impact
      ↓
Repair or ask teacher
```

This makes the system graceful instead of brittle.

---

# 13. Hard Constraints vs Soft Constraints

Not every requirement should be treated identically.

### Hard constraints

Examples:

```text
Question count
Invalid question
Duplicate ID
Missing answer
Non-positive marks
Strict total marks requirement
```

A violation normally means:

```text
Reject candidate
```

### Soft/distribution constraints

Examples:

```text
Algebra target = 20 marks
Actual = 18 marks
```

If a tolerance exists, this can potentially be accepted.

The system can therefore distinguish:

```text
Impossible hard violation
```

from:

```text
Small distribution deviation
```

This is essential for graceful behavior.

---

# 14. Marks-Based Constraints

For a percentage `p` and total marks `T`:

```text
target_marks = T × p
```

Example:

```text
Total = 40
Algebra = 50%
```

Therefore:

```text
40 × 0.50 = 20
```

The evaluator calculates the actual Algebra marks.

If:

```text
actual = 18
target = 20
```

then:

```text
deviation = |18 - 20|
          = 2
```

The configured tolerance determines whether this is acceptable.

---

# 15. Reachable Marks

The Question Intelligence Agent can also reason about which mark totals can actually be constructed.

Conceptually:

```text
R = {0}
```

For each available mark value `m`:

```text
R_new = R ∪ {r + m | r ∈ R}
```

This gives a set of reachable totals.

For example, if the available marks make:

```text
40
```

unreachable, the system can identify that before wasting repeated generation attempts.

This is another example of:

```text
Analyze availability first
rather than blindly generating
```

---

# 16. What If 20% Hard Questions Cannot Be Met?

Suppose:

```text
Total = 40

Hard target:
20% = 8 marks
```

But the available Hard questions can only provide:

```text
6 marks
```

The system should not return:

```text
Hard = 20%
```

because it would be false.

Instead:

```text
Requested:
8 Hard marks

Available feasible maximum:
6 Hard marks

Deviation:
2 marks
```

The system can then either:

```text
Attempt repair
```

or:

```text
Report the constraint conflict
```

or:

```text
Ask teacher whether the requirement may be relaxed
```

depending on the configured policy.

---

# 17. The Key Principle for Constraint Conflicts

The system follows:

> **Never silently change a teacher's constraint.**

If a requirement cannot be satisfied:

```text
Detect
→ explain
→ attempt controlled repair
→ re-evaluate
→ escalate when necessary
```

This is preferable to silently producing a paper that looks correct.

---

# 18. Paper Generation Is Not Random Selection

The Paper Generation Agent does not simply do:

```python
random.sample(question_bank, 8)
```

It constructs the paper according to the blueprint.

Candidate selection considers:

```text
Topic
Difficulty
Question Type
Marks
Uniqueness
Answer availability
Current paper state
```

This creates a structured paper.

---

# 19. Making the Paper Feel Like a Real Exam

Numerical correctness alone is not sufficient.

A paper could satisfy:

```text
40 marks
8 questions
50% Algebra
50% Geometry
```

and still feel poor if it contains:

```text
five nearly identical questions
```

or:

```text
three very difficult questions consecutively
```

or:

```text
the same topic repeatedly
```

Therefore the evaluation layer checks paper-level quality.

The LLM can assess:

```text
Clarity
Relevance
Difficulty consistency
Semantic duplication
Question diversity
Difficulty progression
Topic spread
Section coherence
Overall paper quality
```

The important point is that **the paper is evaluated as a whole**, not only question-by-question.

---

# 20. Difficulty Progression

A real paper often benefits from a sensible progression.

For example:

```text
Easy
Easy
Medium
Medium
Medium
Hard
Hard
```

rather than:

```text
Hard
Easy
Hard
Easy
Medium
Hard
Easy
Medium
```

The system can therefore evaluate whether the ordering appears coherent.

This is a qualitative property, so the LLM is useful here.

---

# 21. Question Diversity

The evaluator checks for semantic repetition.

For example:

```text
Q1:
Solve x² + 5x + 6 = 0.

Q5:
Find the roots of x² + 5x + 6 = 0.
```

These may be structurally different strings but effectively the same question.

A deterministic exact-text check may miss this.

An LLM-based semantic evaluation can flag it.

---

# 22. Why Not Use Only Random Selection?

Random selection can produce:

```text
Duplicate concepts
Bad difficulty distribution
Wrong topic balance
Impossible mark totals
Poor progression
```

The system therefore uses the blueprint and current paper state during selection.

The LLM may help with reasoning, but objective constraints are verified deterministically.

---

# 23. One-Question Swap

The system supports:

```text
"Swap Q4."
```

without regenerating the complete paper.

The current state already contains:

```text
Current Paper
Blueprint
Used IDs
Question Bank
Evaluation
```

So Q4 can be removed temporarily while all other questions remain fixed.

---

# 24. Candidate Replacement

Suppose:

```text
Original Q4:

Algebra
Medium
Short
4 marks
```

Possible candidates:

```text
ALG-011
Algebra
Medium
Short
4 marks

ALG-014
Algebra
Hard
Short
4 marks

GEO-008
Geometry
Medium
Short
4 marks

ALG-021
Algebra
Medium
Long
6 marks
```

The system should not simply select the first available candidate.

It evaluates the effect of each candidate on the current paper.

---

# 25. Cost-Based Replacement

This is where the swap mechanism becomes more intelligent.

Conceptually:

```text
candidate_cost =
      topic_penalty
    + difficulty_penalty
    + type_penalty
    + marks_penalty
    + duplicate_penalty
    + constraint_violation_penalty
```

The cost measures:

> **How much does this candidate disturb the current paper?**

The exact weighting can be configured.

Hard constraint violations receive a much larger penalty or cause outright rejection.

---

# 26. Example of Candidate Cost

Suppose:

```text
Current paper:

Algebra = 20 marks
Geometry = 20 marks

Target:

Algebra = 20
Geometry = 20
```

Original question:

```text
Algebra
Medium
Short
4 marks
```

Candidate A:

```text
Algebra
Medium
Short
4 marks
```

Candidate B:

```text
Algebra
Hard
Short
4 marks
```

Candidate C:

```text
Geometry
Medium
Short
6 marks
```

Candidate A preserves:

```text
Topic
Difficulty
Type
Marks
```

Candidate B changes:

```text
Difficulty distribution
```

Candidate C changes:

```text
Topic distribution
Total marks
```

Therefore Candidate A has the smallest disturbance.

---

# 27. The Important Point: Cost Is Calculated Against the Whole Paper

The candidate is not evaluated in isolation.

The system effectively simulates:

```text
Current Paper
-
Original Question
+
Candidate
```

Then it recalculates:

```text
Total marks
Topic distribution
Difficulty distribution
Question-type distribution
Uniqueness
```

For example:

```text
Before:

Total = 40
Algebra = 20
Geometry = 20
```

If a replacement changes:

```text
Algebra 4 marks
```

to:

```text
Geometry 6 marks
```

then:

```text
Total = 42
Algebra = 16
Geometry = 26
```

The candidate is therefore expensive because it affects several constraints simultaneously.

---

# 28. Candidate Simulation

The swap algorithm is conceptually:

```text
Failed / selected question
          ↓
Generate eligible candidates
          ↓
Remove questions already in paper
          ↓
Validate candidates
          ↓
Temporarily insert candidate
          ↓
Recalculate complete paper
          ↓
Calculate constraint deviation
          ↓
Calculate candidate cost
          ↓
Reject hard violations
          ↓
Choose lowest-cost feasible candidate
```

This is not simply:

```text
Find another Algebra question.
```

It is:

> **Find the replacement that produces the smallest acceptable change to the complete paper.**

---

# 29. Local Change, Global Verification

After choosing the lowest-cost candidate, the system still performs full evaluation.

This is critical.

The rule is:

```text
Lowest-cost candidate
        ≠
Automatically valid
```

Instead:

```text
Lowest-cost candidate
        ↓
Complete paper recalculation
        ↓
Deterministic evaluation
        ↓
LLM quality evaluation
        ↓
PASS / REPAIR / HUMAN
```

Therefore the swap mechanism is:

> **Local modification with global verification.**

---

# 30. Why Not Regenerate the Whole Paper?

Without targeted repair:

```text
Q3 fails
 ↓
Discard entire paper
 ↓
Generate 8 questions again
 ↓
Evaluate again
```

This causes:

```text
More LLM calls
More tokens
More latency
More cost
More unnecessary changes
```

With targeted repair:

```text
Q3 fails
 ↓
Keep valid questions
 ↓
Replace Q3
 ↓
Evaluate updated paper
```

This is much more efficient.

---

# 31. Teacher-Initiated Swap

The same mechanism works even when the question is not objectively wrong.

The teacher may say:

```text
"Replace Q4."
```

The system:

```text
Loads current paper
       ↓
Identifies Q4
       ↓
Keeps other questions fixed
       ↓
Finds candidate replacements
       ↓
Calculates candidate cost
       ↓
Selects feasible replacement
       ↓
Re-evaluates complete paper
```

The teacher therefore gets a local editing experience without rebuilding the paper.

---

# 32. Targeted Regeneration After Evaluation

Suppose:

```text
Q3 = unclear
```

The evaluator records:

```text
affected_question_ids = ["Q3"]
```

The generator receives:

```text
Current Paper
Blueprint
Question Bank
Failure
Affected Question
```

It generates/selects a replacement.

Then:

```text
Replacement
     ↓
Global evaluation
```

If the paper passes:

```text
PASS
```

Otherwise another repair attempt can occur.

---

# 33. LLM vs Deterministic Logic

The architecture is deliberately hybrid.

## LLM

Used for:

```text
Requirement interpretation
Qualitative question evaluation
Semantic duplicate detection
Clarity
Relevance
Difficulty consistency
Paper coherence
```

## Deterministic logic

Used for:

```text
Marks
Counts
Percentages
Duplicates
Schema
Distribution
Hard constraints
```

This division is intentional.

---

# 34. Why Not Give Everything to the LLM?

An LLM should not be responsible for exact arithmetic.

For example:

```text
Required = 40 marks
Actual = 38 marks
```

This is a deterministic fact.

Likewise:

```text
Question count = 8
```

should be calculated directly.

If an LLM is allowed to declare:

```text
"This paper seems to have 40 marks."
```

the system is less reliable.

Therefore exact constraints are enforced in code.

---

# 35. Why Not Use Only Deterministic Logic?

Rules cannot reliably answer questions such as:

```text
Is this question clear?

Is the answer actually correct?

Are these two questions semantically duplicates?

Does the difficulty match the requested level?

Does the paper feel coherent?
```

These require semantic reasoning.

Therefore the LLM is useful as a qualitative evaluator.

---

# 36. The Hybrid Principle

The architecture can be summarized as:

```text
LLM
→ understand and judge qualitative properties

Deterministic logic
→ calculate and enforce exact properties
```

This reduces the weaknesses of using either approach alone.

---

# 37. Evaluation Architecture

The Evaluation Agent has two major layers.

### Deterministic verifier

```text
Question count
Total marks
Topic distribution
Difficulty distribution
Question-type distribution
Duplicate IDs
Exact duplicates
Structural validity
```

### LLM evaluator

```text
Relevance
Clarity
Answerability
Answer correctness
Difficulty consistency
Semantic duplicates
Paper coherence
```

The two results are combined into a routing decision.

---

# 38. Confidence-Based Routing

The qualitative evaluator can provide confidence.

Conceptually:

```text
confidence >= 0.90
```

can support automatic action.

For example:

```text
High-confidence question problem
        ↓
Targeted regeneration
```

Medium confidence can trigger:

```text
Second evaluation
```

Low confidence can trigger:

```text
Human review
```

This prevents the LLM from making uncertain decisions automatically.

---

# 39. Human-in-the-Loop

Human review is important when:

```text
Constraints conflict
```

or:

```text
The evaluator is uncertain
```

or:

```text
Multiple acceptable repairs exist
```

The teacher can decide:

```text
Approve
Swap
Regenerate
Relax a requirement
Reject
```

The system therefore assists the teacher rather than silently making important changes.

---

# 40. Example — Impossible Hard Algebra Requirement

Suppose the teacher requests:

```text
40 marks

20% Hard
50% Algebra
50% Geometry
```

and the question bank contains:

```text
Hard Algebra = 0 marks available
Hard Geometry = enough
Medium Algebra = enough
```

The system detects:

```text
Hard + Algebra
```

as the problematic combination.

It can report:

```text
Hard Algebra requirement cannot currently be satisfied.

Available alternatives:

1. Use Hard Geometry
2. Use Medium Algebra
3. Relax the Hard percentage
4. Allow generation of new questions
```

The teacher can then choose.

The system does not silently choose one.

---

# 41. Example — One Question Swap

Current:

```text
Q1 Algebra Easy MCQ 2
Q2 Geometry Easy MCQ 2
Q3 Algebra Medium Short 4
Q4 Geometry Medium Short 4
Q5 Algebra Medium Short 4
Q6 Geometry Medium Short 4
Q7 Algebra Hard Long 10
Q8 Geometry Hard Long 10
```

Teacher:

```text
"Swap Q3."
```

Q3 is:

```text
Algebra
Medium
Short
4
```

The system temporarily removes Q3.

Candidate:

```text
ALG-012
Algebra
Medium
Short
4
```

is evaluated.

Because the candidate preserves:

```text
Topic
Difficulty
Type
Marks
```

the paper distribution remains unchanged.

The system then runs the complete evaluator again.

---

# 42. Why Cost-Based Swap Is Useful

Suppose an exact replacement is unavailable.

The system might have:

```text
Candidate A:
Algebra / Hard / Short / 4

Candidate B:
Geometry / Medium / Short / 4

Candidate C:
Algebra / Medium / Long / 6
```

All may be structurally valid.

The system calculates their consequences.

Conceptually:

```text
A → changes difficulty

B → changes topic

C → changes type + marks
```

The cost function captures these differences.

Therefore the replacement is based on **minimum constraint disturbance**, not arbitrary selection.

---

# 43. Conflict Subset and Cost-Based Repair Work Together

These are two different but connected mechanisms.

### Conflict subset

Answers:

> **What combination of constraints is causing the problem?**

Example:

```text
Algebra + Hard + MCQ
```

### Candidate cost

Answers:

> **Given the problem, which replacement causes the smallest acceptable disturbance?**

Example:

```text
Candidate A → cost 0
Candidate B → cost 4
Candidate C → cost 8
```

Together:

```text
Detect conflict
      ↓
Localize conflict
      ↓
Find feasible alternatives
      ↓
Calculate repair cost
      ↓
Choose feasible low-cost repair
      ↓
Globally verify
```

This makes the repair process much more controlled.

---

# 44. Important Distinction — Do Not Pretend Constraints Were Satisfied

Suppose:

```text
Requested Hard = 8 marks
Actual Hard = 6 marks
```

The system should report:

```text
Hard target: 8
Actual: 6
Deviation: 2
Status: outside requested target
```

It should **not** simply relabel another question as Hard to make the numbers look correct.

The metadata must reflect the actual question.

---

# 45. Question Bank Validation

Every question is validated using Pydantic.

Fields include:

```text
id
text
topic
difficulty
question_type
marks
answer
```

The system also normalizes metadata:

```text
Algebra → algebra
ALGEBRA → algebra

Easy → easy
EASY → easy

MCQ → mcq
Mcq → mcq
```

This avoids false mismatches.

---

# 46. Duplicate Protection

During generation and swapping, already-used IDs are excluded.

For example:

```text
Used:

Q1,Q2,Q3,Q4,Q5,Q6,Q7,Q8
```

When Q3 is being replaced:

```text
Q1,Q2,Q4,Q5,Q6,Q7,Q8
```

remain unavailable for reuse.

The evaluator also checks:

```text
len(ids) == len(set(ids))
```

This provides deterministic duplicate detection.

---

# 47. Exact Duplicate Detection

Question text is normalized before comparison.

Conceptually:

```python
" ".join(text.lower().split())
```

So:

```text
Solve x + 2 = 5.
```

and:

```text
solve   x + 2 = 5.
```

are treated as identical.

Semantic duplication is handled separately by the qualitative evaluator.

---

# 48. Why JSON Is Used at Runtime

The original question bank is provided as PDF material.

Runtime processing uses structured JSON:

```text
PDF
 ↓
question_bank.json
 ↓
Validation
 ↓
Inventory
 ↓
Generation
 ↓
Evaluation
```

PDF is good for human reading.

JSON is better for:

```text
Filtering
Lookup
Metadata
Validation
Inventory
Duplicate detection
Candidate selection
```

---

# 49. End-to-End Flow

The complete system works as:

```text
Teacher
   ↓
Blueprint Agent
   ↓
Question Intelligence
   ↓
Inventory + Feasibility
   ↓
Conflict analysis
   ↓
Paper Generation
   ↓
Candidate Paper
   ↓
Deterministic Evaluation
   ↓
LLM Quality Evaluation
   ↓
Routing
```

Then:

```text
PASS
```

or:

```text
REPAIR
```

or:

```text
TARGETED REGENERATION
```

or:

```text
HUMAN REVIEW
```

---

# 50. Full Conflict-Repair Loop

The interesting part can be summarized as:

```text
                 TEACHER REQUIREMENTS
                          │
                          ▼
                    BLUEPRINT
                          │
                          ▼
                 QUESTION INTELLIGENCE
                          │
                          ▼
              AVAILABLE COMBINATIONS
                          │
                          ▼
                 CONFLICT ANALYSIS
                          │
              ┌───────────┴────────────┐
              │                        │
       No conflict               Conflict found
              │                        │
              ▼                        ▼
         Generation             Identify subset
                                       │
                                       ▼
                              Find feasible options
                                       │
                                       ▼
                               Calculate impact/cost
                                       │
                            ┌──────────┴─────────┐
                            │                    │
                      Feasible repair      No safe repair
                            │                    │
                            ▼                    ▼
                     Targeted repair       Human review
                            │
                            ▼
                       Full evaluation
                            │
                            ▼
                           PASS
```

---

# 51. Why This Is Graceful

The system has multiple levels of protection.

### Level 1 — Understand availability

```text
What questions actually exist?
```

### Level 2 — Detect conflicts

```text
Which combination cannot be satisfied?
```

### Level 3 — Attempt repair

```text
Can we find a feasible low-cost alternative?
```

### Level 4 — Recalculate

```text
Did the repair break another constraint?
```

### Level 5 — Re-evaluate

```text
Does the complete paper still pass?
```

### Level 6 — Human escalation

```text
If automation cannot safely decide, ask the teacher.
```

This is much safer than:

```text
Generate → hope → return
```

---

# 52. Why State Matters for Conflict Repair

Imagine:

```text
Paper = Q1,Q2,Q3,Q4,Q5,Q6,Q7,Q8
```

and:

```text
Q3 causes conflict.
```

Without state:

```text
Regenerate complete paper
```

With state:

```text
Remember Q1,Q2,Q4,Q5,Q6,Q7,Q8
        ↓
Repair Q3
```

The system therefore preserves successful work.

---

# 53. Why State Matters for Teacher Swaps

If a teacher says:

```text
"Swap Q4."
```

the system does not need:

```text
Teacher requirements again
```

because the state already contains:

```text
Blueprint
Current paper
Question bank
Used IDs
Evaluation
```

The operation becomes:

```text
Current state
    ↓
Remove Q4
    ↓
Generate candidates
    ↓
Cost comparison
    ↓
Insert replacement
    ↓
Global evaluation
```

---

# 54. Cost and Latency

Targeted regeneration reduces unnecessary work.

Instead of:

```text
8 questions generated
8 questions regenerated
```

the system can perform:

```text
8 questions generated
1 question regenerated
```

This reduces:

```text
LLM calls
Token usage
Latency
Cost
```

It also preserves questions the teacher has already accepted.

---

# 55. Why the System Does Not Need CP-SAT / OR-Tools

The design intentionally does not rely on CP-SAT or OR-Tools.

The architecture uses:

```text
Question Intelligence
+
Deterministic validation
+
Constraint deviation
+
Candidate cost
+
Targeted repair
```

This keeps the logic transparent and easier to explain.

The system is not hiding the entire selection process inside an optimization solver.

---

# 56. What I Would Say in a Viva

If asked:

> **"What happens if the constraints don't fit?"**

I would answer:

> "I don't let the LLM silently compromise the requirements. First, the Question Intelligence Agent analyzes the actual question bank and builds a multidimensional inventory, including topic, difficulty, question type and their combinations. If a requested combination is unavailable, I localize the conflict to the smallest relevant subset rather than declaring the entire request impossible. For example, Algebra may exist, Hard questions may exist, and MCQs may exist, but Hard Algebra MCQs may not. I can then identify that intersection as the conflict, calculate feasible alternatives, and either perform a controlled repair or ask the teacher to relax a requirement. After every repair I run the complete deterministic evaluator again."

If asked:

> **"How do you swap one question?"**

I would say:

> "The paper is maintained in LangGraph state. When one question needs replacement, I keep the valid questions fixed and generate candidate replacements for only that position. Each candidate is simulated against the current paper and gets a cost based on how much it changes topic, difficulty, type, marks and other constraints. I choose the lowest-cost feasible candidate, then re-evaluate the entire paper. So the modification is local, but validation is global."

If asked:

> **"Why hybrid AI and logic?"**

I would say:

> "LLMs are good at language understanding and qualitative evaluation, but exact constraints should not depend on an LLM. Marks, counts, percentages and duplicates are deterministic, so I enforce them in code. Semantic duplication, clarity, relevance and paper coherence are harder to express as rules, so I use an LLM there. The hybrid design gives me flexible reasoning with strict numerical verification."

If asked:

> **"How do you make it feel like a real paper?"**

I would say:

> "I don't use random selection. The generator constructs the paper against the blueprint and the available question-bank metadata. Then the evaluator checks both objective distributions and qualitative paper-level properties such as diversity, difficulty consistency, topic spread, semantic duplication and coherence."

---

# 57. The Three Most Important Design Ideas

The project can ultimately be explained through three ideas.

### 1. Detect conflicts instead of hiding them

```text
Requested constraints
        ↓
Question-bank analysis
        ↓
Conflict subset
        ↓
Explain exact problem
```

### 2. Repair locally

```text
Bad question
      ↓
Candidate replacements
      ↓
Cost comparison
      ↓
Replace one question
```

### 3. Verify globally

```text
Local replacement
      ↓
Complete paper
      ↓
Full deterministic + LLM evaluation
```

So the core philosophy is:

> **Local repair, global verification, and transparent conflict handling.**

---

# 58. Final Summary

The complete architecture is:

```text
Teacher
   ↓
Blueprint Agent
   ↓
Question Intelligence
   ↓
Inventory + Feasibility
   ↓
Conflict Subset Detection
   ↓
Paper Generation
   ↓
Deterministic Evaluation
   ↓
LLM Quality Evaluation
   ↓
Routing
   │
   ├── PASS
   │
   ├── Targeted Repair
   │       ↓
   │   Candidate Cost
   │       ↓
   │   Replacement
   │       ↓
   │   Global Evaluation
   │
   └── Human Review
```

The main architectural principle is:

> **LLM for understanding and qualitative reasoning, deterministic logic for exact correctness, Question Intelligence for knowing what is actually possible, state-aware LangGraph execution for preserving context, conflict-subset analysis for diagnosing infeasibility, cost-based targeted repair for efficient swapping, and human review when the system cannot safely resolve a conflict.**

The key repair principle is:

> **Change locally, validate globally.**

And the key conflict principle is:

> **Do not silently ignore an impossible constraint. Identify the conflicting subset, explain it, attempt the smallest controlled repair, and escalate to the teacher when a safe automatic decision cannot be made.**
