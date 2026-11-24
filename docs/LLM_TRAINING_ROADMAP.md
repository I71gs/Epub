# LLM Improvement and Training Roadmap

This roadmap describes how to use paired book PDFs and audiobooks to improve the
AI Audiobook Maker. It favors measuring the existing workflow and using
pretrained models before committing to fine-tuning or training.

## Goal

Improve end-to-end processing efficiency without reducing audiobook quality.
Track at least:

- Processing time per book and per chapter.
- LLM/API cost per book, if applicable.
- Quality of extracted text, scene boundaries, dialogue attribution, and
  narration plans.
- Failure and retry rates, including cases where human review is needed.

Record a baseline before changing models. Compare improvements against the same
books and evaluation criteria.

## Important constraints

- Use only PDFs and audiobook recordings that you own, are public domain, or
  have explicit permission to use for this purpose. Check whether the license
  permits creating training data and model derivatives.
- An audiobook is audio data, not a ready-made text-LLM training example. For
  text-model experiments, transcribe and align the audio first. Speech
  transcription or voice generation are separate tasks that use speech models.
- A recording may be abridged, edited, or based on a different edition than the
  PDF. Do not assume every spoken sentence will match the PDF.
- The GTX 970M is an older GPU. Check its exact VRAM, driver, and framework
  compatibility before choosing local models; do not assume it can fine-tune a
  modern LLM. A cloud GPU may be needed for fine-tuning.
- Do not train a voice-cloning model as part of this LLM work. Voice generation
  has different data, consent, and evaluation requirements.

## Steps

### 1. Select one improvement target

The project already has LLM-backed book analysis, scene analysis,
character/dialogue extraction, and narration planning in
`app/book/intelligence.py`. Choose one task to improve first rather than
training for an undefined "end-to-end" objective.

Suggested first targets:

1. Reduce repeated LLM calls with reliable caching and reuse.
2. Improve scene or dialogue analysis using reviewed examples.
3. Improve narration plans while preserving the original book text.
4. Explore transcription/alignment separately if speech recognition is the
   bottleneck.

Define what counts as a correct result and what latency or cost improvement is
worth pursuing.

### 2. Establish the baseline

Run the current workflow on a small set of representative, rights-cleared
books. Record:

- Input book edition, language, and whether the audiobook is abridged.
- Runtime, API/model used, number of calls, and cost if available.
- Output quality using a small human-reviewed checklist for the selected task.
- Common failure cases and how much correction they require.

Keep the baseline outputs so later model experiments can be compared against
them.

### 3. Prepare and validate paired sources

For each book:

1. Extract text and page/chapter boundaries from the PDF; inspect extraction
   quality, especially for scanned pages.
2. Transcribe the audiobook with a suitable pretrained speech-recognition
   model.
3. Align the transcript to the PDF text and retain timestamps and source
   references where available.
4. Mark omissions, additions, and mismatches rather than forcing a false
   alignment.
5. Have a person review a sample of each pair before using it as a label.

Keep originals read-only and store derived text, transcripts, alignment
metadata, and review status separately. Avoid putting copyrighted source text
or audio into public repositories or unapproved hosted services.

### 4. Create a small, reviewed evaluation dataset

Build examples for the selected target from aligned material. Store only the
minimum fields needed, such as input text, expected structured output, source
book identifier, and review status.

Split data by **book**, not by paragraph or scene, into training, validation,
and test sets. This prevents passages from the same book appearing in both
training and evaluation and making results look better than they are.

Validate examples against the project's Pydantic models where possible, such
as `SceneProfile`, `DialogueSegment`, and `NarrationPlan` in
`app/book/models.py`. Preserve the source text exactly when the task is
analysis or narration planning; model-generated summaries or plans should not
silently rewrite the book.

### 5. Try lower-cost approaches before fine-tuning

Use the baseline to determine whether the bottleneck is model quality, repeated
calls, prompt size, or data preparation. Test these options in order:

1. Improve prompt instructions and structured-output validation.
2. Reuse the existing cache and avoid repeating unchanged analyses.
3. Batch or shorten requests where this preserves output quality.
4. Compare a suitable pretrained model, including a local model if hardware
   permits.
5. Fine-tune only if a reviewed dataset shows a persistent, measurable error
   that prompting and model selection do not fix.

For a fine-tuning experiment, prefer parameter-efficient tuning of a suitable
pretrained model over training from scratch. Use a cloud GPU if the GTX 970M
cannot support the chosen model and training method.

### 6. Evaluate against the baseline

Run the same held-out books through the existing and candidate approaches.
Compare:

- Task-specific quality, using human review for subjective results.
- Schema validity and missing/incorrect fields.
- Runtime, API cost, and GPU/memory requirements.
- Robustness across book genres, languages, and PDF quality.

Do not adopt a model based only on training loss or one successful book. Keep
the current model as a fallback until the candidate consistently meets the
quality target and improves the agreed efficiency measure.

### 7. Integrate behind the existing adapter

`app/book/intelligence.py` defines an `LLMAdapter` interface, which is the
natural boundary for experimenting with another provider or a local model.
Keep model selection configurable and avoid coupling book analysis to a
specific model library. Add focused tests for structured outputs, malformed
responses, fallback behavior, and cache compatibility.

Log model/version and timing metadata without logging full copyrighted book
text by default. Document setup and data handling before enabling the model
outside development.

## First milestone

Complete a pilot using one rights-cleared PDF/audiobook pair:

- Verify that the PDF is extractable and the audiobook is suitable for
  transcription.
- Create and manually inspect a small aligned sample.
- Choose one task and define its quality and efficiency measures.
- Run the current implementation as the baseline.
- Decide from measured results whether better prompting, caching, model
  replacement, or fine-tuning is justified.

Do not begin full-dataset fine-tuning until this pilot demonstrates that the
training examples are accurate, permitted, and useful.
