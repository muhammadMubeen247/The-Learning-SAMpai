"""
Unified prompt templates for the FYP RAG engine.
Combines LightRAG's KG extraction/query prompts with RAG-Anything's multimodal prompts.
"""
from __future__ import annotations
from typing import Any

PROMPTS: dict[str, Any] = {}

# ---------------------------------------------------------------------------
# Delimiters
# ---------------------------------------------------------------------------
PROMPTS["DEFAULT_TUPLE_DELIMITER"] = "<|#|>"
PROMPTS["DEFAULT_COMPLETION_DELIMITER"] = "<|COMPLETE|>"

# ---------------------------------------------------------------------------
# Entity & Relation Extraction (from LightRAG)
# ---------------------------------------------------------------------------

PROMPTS["entity_extraction_system_prompt"] = """---Role---
You are a Knowledge Graph Specialist responsible for extracting entities and relationships from the input text.

---Instructions---
1.  **Entity Extraction & Output:**
    *   **Identification:** Identify clearly defined and meaningful entities in the input text.
    *   **Entity Details:** For each identified entity, extract the following information:
        *   `entity_name`: The name of the entity. Capitalize the first letter of each significant word (title case). Ensure **consistent naming** across the entire extraction process.
        *   `entity_type`: Categorize using one of: `{entity_types}`. If none apply, use `Other`.
        *   `entity_description`: A concise yet comprehensive description based *solely* on the input text.
    *   **Output Format - Entities:** 4 fields delimited by `{tuple_delimiter}` on a single line. First field must be literal `entity`.
        *   Format: `entity{tuple_delimiter}entity_name{tuple_delimiter}entity_type{tuple_delimiter}entity_description`

2.  **Relationship Extraction & Output:**
    *   **Identification:** Identify direct, clearly stated relationships between extracted entities.
    *   **Relationship Details:**
        *   `source_entity`: Source entity name (title case, consistent with extraction).
        *   `target_entity`: Target entity name (title case, consistent with extraction).
        *   `relationship_keywords`: High-level keywords (comma-separated, NOT using `{tuple_delimiter}`).
        *   `relationship_description`: A concise explanation of the relationship.
    *   **Output Format - Relationships:** 5 fields delimited by `{tuple_delimiter}`. First field must be literal `relation`.
        *   Format: `relation{tuple_delimiter}source_entity{tuple_delimiter}target_entity{tuple_delimiter}relationship_keywords{tuple_delimiter}relationship_description`

3.  **Delimiter Usage:** `{tuple_delimiter}` is a field separator — never fill it with content.

4.  **Relationship Direction:** Treat all relationships as **undirected**. Avoid duplicate relationships.

5.  **Output Order:** All entities first, then all relationships (most significant first).

6.  **Context:** Write in third person. Avoid pronouns; use explicit names.

7.  **Language:** Output in `{language}`. Retain proper nouns in original language.

8.  **Completion Signal:** Output `{completion_delimiter}` after all extractions.

---Examples---
{examples}
"""

PROMPTS["entity_extraction_user_prompt"] = """---Task---
Extract entities and relationships from the input text below.

---Instructions---
1. Strictly adhere to format requirements from the system prompt.
2. Output *only* the extracted list. No introductory or concluding remarks.
3. Output `{completion_delimiter}` as the final line.
4. Output language: {language}.

---Data to be Processed---
<Entity_types>
[{entity_types}]

<Input Text>
```
{input_text}
```

<Output>
"""

PROMPTS["entity_continue_extraction_user_prompt"] = """---Task---
Based on the last extraction task, identify and extract any **missed or incorrectly formatted** entities and relationships.

---Instructions---
1. **Do NOT** re-output correctly extracted items from the last task.
2. Only output missed or incorrectly formatted entities/relationships.
3. Format - Entities: `entity{tuple_delimiter}entity_name{tuple_delimiter}entity_type{tuple_delimiter}entity_description`
4. Format - Relationships: `relation{tuple_delimiter}source{tuple_delimiter}target{tuple_delimiter}keywords{tuple_delimiter}description`
5. Output `{completion_delimiter}` as the final line.
6. Output language: {language}.

<Output>
"""

PROMPTS["entity_extraction_examples"] = [
    """<Entity_types>
["Person","Organization","Location","Event","Concept","Method","Course","Definition","Formula","Theory","Algorithm"]

<Input Text>
```
Newton's Second Law states that the net force on an object equals the product of its mass and acceleration (F = ma).
This fundamental principle in classical mechanics was developed by Sir Isaac Newton in the 17th century.
```

<Output>
entity<|#|>Newton's Second Law<|#|>Formula<|#|>Newton's Second Law states that the net force on an object equals the product of its mass and acceleration, expressed as F = ma.
entity<|#|>Sir Isaac Newton<|#|>Person<|#|>Sir Isaac Newton is a 17th-century physicist and mathematician who developed Newton's Second Law and classical mechanics.
entity<|#|>Classical Mechanics<|#|>Concept<|#|>Classical mechanics is a branch of physics that studies the motion of objects; Newton's Second Law is a foundational principle within it.
relation<|#|>Newton's Second Law<|#|>Classical Mechanics<|#|>foundational principle, physics<|#|>Newton's Second Law is a fundamental principle of classical mechanics.
relation<|#|>Sir Isaac Newton<|#|>Newton's Second Law<|#|>discovery, physics<|#|>Sir Isaac Newton developed Newton's Second Law in the 17th century.
<|COMPLETE|>

""",
]

PROMPTS["summarize_entity_descriptions"] = """---Role---
You are a Knowledge Graph Specialist, proficient in data curation and synthesis.

---Task---
Synthesize a list of descriptions of a given entity or relation into a single, comprehensive, cohesive summary.

---Instructions---
1. Integrate all key information from every provided description. Do not omit important facts.
2. Write from an objective, third-person perspective. Explicitly mention the entity/relation name.
3. Handle conflicting descriptions by reconciling or presenting both viewpoints.
4. Length: Do not exceed {summary_length} tokens.
5. Language: {language}.

---Input---
{description_type} Name: {description_name}

Description List:

```
{description_list}
```

---Output---
"""

PROMPTS["fail_response"] = "Sorry, I'm not able to provide an answer to that question.[no-context]"

# ---------------------------------------------------------------------------
# Query response prompts (from LightRAG)
# ---------------------------------------------------------------------------

PROMPTS["rag_response"] = """---Role---

You are an intelligent, friendly educational assistant helping students understand their course materials.
Answer the user's question accurately using ONLY the information from the provided **Context**.

---Goal---

Generate a comprehensive, well-structured answer that integrates relevant facts from the Knowledge Graph and Document Chunks.
The context may include descriptions of **images, diagrams, tables, and equations** extracted from the document — treat these visual descriptions as first-class evidence and reference them explicitly when relevant (e.g. "According to the architecture diagram..." or "As shown in the system overview image...").
Consider the conversation history to maintain context and avoid repeating information.

---Instructions---

1. Use only the provided context — do NOT invent or assume information.
2. If the answer is not in the context, say you don't have enough information.
3. Use Markdown formatting (headings, bold, bullet points) for clarity.
4. When the context includes image or diagram descriptions, explicitly mention what the visual shows.
5. Response style: {response_type}.
6. Additional instructions: {user_prompt}

---Context---

{context_data}
"""

PROMPTS["naive_rag_response"] = """---Role---

You are an intelligent, friendly educational assistant helping students understand their course materials.
Answer the user's question accurately using ONLY the information from the provided **Context**.

---Goal---

Generate a comprehensive, well-structured answer using the Document Chunks in the Context.
Consider the conversation history to maintain context.

---Instructions---

1. Use only the provided context — do NOT invent or assume information.
2. If the answer is not in the context, say you don't have enough information.
3. Use Markdown formatting for clarity.
4. Response style: {response_type}.
5. Additional instructions: {user_prompt}

---Context---

{content_data}
"""

PROMPTS["kg_query_context"] = """
Knowledge Graph Data (Entities):

```json
{entities_str}
```

Knowledge Graph Data (Relationships):

```json
{relations_str}
```

Document Chunks:

```json
{text_chunks_str}
```

Reference Document List:

```
{reference_list_str}
```

"""

PROMPTS["naive_query_context"] = """
Document Chunks:

```json
{text_chunks_str}
```

Reference Document List:

```
{reference_list_str}
```

"""

# ---------------------------------------------------------------------------
# Keyword extraction for query routing
# ---------------------------------------------------------------------------

PROMPTS["keywords_extraction"] = """---Role---
You are an expert keyword extractor for a RAG system.

---Goal---
Extract two types of keywords from the user query:
1. **high_level_keywords**: overarching concepts or themes.
2. **low_level_keywords**: specific entities, proper nouns, technical terms.

---Instructions---
Output MUST be a valid JSON object only. No markdown, no explanations.
For vague queries, return empty lists.
Language: {language}.

---Examples---
{examples}

---Real Data---
User Query: {query}

---Output---
Output:"""

PROMPTS["keywords_extraction_examples"] = [
    """Example 1:
Query: "What is the relationship between Newton's laws and kinetic energy?"
Output: {"high_level_keywords": ["classical mechanics", "physics principles"], "low_level_keywords": ["Newton's laws", "kinetic energy"]}
""",
    """Example 2:
Query: "Explain gradient descent in machine learning."
Output: {"high_level_keywords": ["optimization", "machine learning"], "low_level_keywords": ["gradient descent", "loss function"]}
""",
]

# ---------------------------------------------------------------------------
# Multimodal prompts (from RAG-Anything)
# ---------------------------------------------------------------------------

PROMPTS["IMAGE_ANALYSIS_SYSTEM"] = (
    "You are an expert image analyst. Provide detailed, accurate descriptions."
)
PROMPTS["TABLE_ANALYSIS_SYSTEM"] = (
    "You are an expert data analyst. Provide detailed table analysis with specific insights."
)
PROMPTS["EQUATION_ANALYSIS_SYSTEM"] = (
    "You are an expert mathematician. Provide detailed mathematical analysis."
)

PROMPTS["vision_prompt"] = """Please analyze this image in detail and provide a JSON response with the following structure:

{{
    "detailed_description": "A comprehensive and detailed visual description of the image:
    - Overall composition and layout
    - All objects, people, text, and visual elements
    - Relationships between elements
    - Colors, lighting, and visual style
    - Any actions or activities shown
    - Technical details if relevant (charts, diagrams, etc.)
    - Always use specific names instead of pronouns",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "image",
        "summary": "concise summary of the image content and its significance (max 100 words)"
    }}
}}

Additional context:
- Image Path: {image_path}
- Captions: {captions}
- Footnotes: {footnotes}

Focus on providing accurate, detailed visual analysis useful for knowledge retrieval."""

PROMPTS["vision_prompt_with_context"] = """Please analyze this image in detail, considering the surrounding context. Provide a JSON response:

{{
    "detailed_description": "Comprehensive visual description:
    - Overall composition and layout
    - All objects, people, text, and visual elements
    - Relationships between elements and how they relate to surrounding context
    - Colors, lighting, and visual style
    - Any actions or activities shown
    - Technical details if relevant
    - Reference connections to surrounding content when relevant
    - Always use specific names instead of pronouns",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "image",
        "summary": "concise summary of image content, significance, and relationship to surrounding content (max 100 words)"
    }}
}}

Context from surrounding content:
{context}

Image details:
- Image Path: {image_path}
- Captions: {captions}
- Footnotes: {footnotes}"""

PROMPTS["table_prompt"] = """Please analyze this table content and provide a JSON response:

{{
    "detailed_description": "Comprehensive table analysis:
    - Table structure and organization
    - Column headers and their meanings
    - Key data points and patterns
    - Statistical insights and trends
    - Relationships between data elements
    - Significance of the data presented
    Always use specific names and values.",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "table",
        "summary": "concise summary of the table's purpose and key findings (max 100 words)"
    }}
}}

Table Information:
Image Path: {table_img_path}
Caption: {table_caption}
Body: {table_body}
Footnotes: {table_footnote}"""

PROMPTS["table_prompt_with_context"] = """Please analyze this table considering the surrounding context, and provide a JSON response:

{{
    "detailed_description": "Comprehensive table analysis including:
    - Table structure and organization
    - Column headers and their meanings
    - Key data points and patterns
    - Statistical insights and trends
    - Significance in relation to surrounding context
    - How the table supports or illustrates surrounding concepts
    Always use specific names and values.",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "table",
        "summary": "concise summary of the table's purpose, findings, and relationship to surrounding content (max 100 words)"
    }}
}}

Context from surrounding content:
{context}

Table Information:
Image Path: {table_img_path}
Caption: {table_caption}
Body: {table_body}
Footnotes: {table_footnote}"""

PROMPTS["equation_prompt"] = """Please analyze this mathematical equation and provide a JSON response:

{{
    "detailed_description": "Comprehensive equation analysis:
    - Mathematical meaning and interpretation
    - Variables and their definitions
    - Mathematical operations and functions used
    - Application domain and context
    - Physical or theoretical significance
    - Relationship to other mathematical concepts
    - Practical applications or use cases
    Always use specific mathematical terminology.",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "equation",
        "summary": "concise summary of the equation's purpose and significance (max 100 words)"
    }}
}}

Equation Information:
Equation: {equation_text}
Format: {equation_format}"""

PROMPTS["equation_prompt_with_context"] = """Please analyze this mathematical equation considering the surrounding context, and provide a JSON response:

{{
    "detailed_description": "Comprehensive equation analysis including:
    - Mathematical meaning and interpretation
    - Variables and their definitions in the context of surrounding content
    - Mathematical operations and functions used
    - Application domain based on surrounding material
    - Physical or theoretical significance
    - Relationship to mathematical concepts mentioned in context
    - Practical applications
    - How the equation relates to the broader discussion
    Always use specific mathematical terminology.",
    "entity_info": {{
        "entity_name": "{entity_name}",
        "entity_type": "equation",
        "summary": "concise summary of the equation's purpose, significance, and role in surrounding context (max 100 words)"
    }}
}}

Context from surrounding content:
{context}

Equation Information:
Equation: {equation_text}
Format: {equation_format}"""

# Modal chunk templates (for storing multimodal content as text chunks)
PROMPTS["image_chunk"] = """Image Content Analysis:
Image Path: {image_path}
Captions: {captions}
Footnotes: {footnotes}

Visual Analysis: {enhanced_caption}"""

PROMPTS["table_chunk"] = """Table Analysis:
Image Path: {table_img_path}
Caption: {table_caption}
Structure: {table_body}
Footnotes: {table_footnote}

Analysis: {enhanced_caption}"""

PROMPTS["equation_chunk"] = """Mathematical Equation Analysis:
Equation: {equation_text}
Format: {equation_format}

Mathematical Analysis: {enhanced_caption}"""
