# Test Fixtures

Sample data for the LLM evaluation framework. Each `.txt` file wraps a JSON payload in a `KafkaMessage(value=b'''...''')` envelope.

| Fixture | Difficulty | What it tests | Expected outcome |
|---|---|---|---|
| **valid_sample.txt** | Easy | Baseline — accurate, faithful, complete | High scores across all metrics |
| **not_valid_sample.txt** | Easy | Blatant hallucination (animals, mitochondria, CO₂ instead of plants, chloroplasts, O₂) | Low Faithfulness, low Answer Relevancy |
| **sample.txt** | Medium | Subtle hallucination — says "1942 Nobel" when context says "1945 Nobel" | Should catch wrong year; tests judge precision |
| **partial_answer.txt** | Hard | Correct but incomplete — names the 3 states but omits how they differ | Low Completeness, possibly low Informativeness |
| **unfaithful_extrapolation.txt** | Hard | First sentence faithful, then adds altitude/Everest claims not in context | Tests Faithfulness boundary — partly faithful, partly fabricated |
| **vague_answer.txt** | Hard | Technically on-topic but gives no specific facts (context has exact number) | Low Informativeness, low Completeness |
| **off_topic_answer.txt** | Hard | Answers about volcanoes when asked about earthquakes | Low Answer Relevancy, low Contextual Relevancy |
| **wrong_event_type.txt** | N/A | Filtered out before eval (`event_type` ≠ `ai-event`) | Skipped by filtering |
| **wrong_system.txt** | N/A | Filtered out before eval (`system` ≠ `enterprise-rag-chatbot`) | Skipped by filtering |
