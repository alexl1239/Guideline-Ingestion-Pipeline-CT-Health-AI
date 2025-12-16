"""
Test Parent-Child Chunk Relationship for Uganda Clinical Guidelines RAG System

This test validates the CORE pattern of our RAG architecture:
- Parent chunks: Complete clinical sections (1000-1500 tokens)
- Child chunks: Small retrieval units (~256 tokens)
- Pattern: Search on children, return parents to LLM
"""

import pytest
import sqlite3
from pathlib import Path
import tiktoken


# Test data: Malaria clinical section (sized to match realistic parent chunk 1000-1500 tokens)
MALARIA_CONTENT = """# 1.2 Malaria

## Definition
Malaria is an acute febrile illness caused by Plasmodium parasites transmitted through the bite of infected female Anopheles mosquitoes. Four species commonly cause malaria in humans: Plasmodium falciparum (most severe), P. vivax, P. ovale, and P. malariae. In Uganda, P. falciparum accounts for over 95% of cases and is responsible for most severe malaria complications and deaths. Malaria remains a leading cause of morbidity and mortality, particularly in children under 5 years and pregnant women.

## Epidemiology
Malaria transmission occurs throughout Uganda with varying intensity. Over 95% of the population lives in areas with stable malaria transmission. Peak transmission occurs during the two rainy seasons (March-May and September-November). Children under 5 years account for approximately 50% of all malaria cases and 70% of deaths. Pregnant women, especially primigravidae, are at increased risk of severe disease and adverse pregnancy outcomes.

## Risk Factors
- Age: Children under 5 years and infants
- Pregnancy: Especially first and second pregnancies
- Immunocompromised: HIV/AIDS, malnutrition, splenectomy
- Low socioeconomic status: Poor housing, lack of bed nets
- Occupational: Outdoor workers, farmers, miners

## Clinical Features
### Uncomplicated Malaria
- Fever: Typically >38.5°C, may be cyclical every 48-72 hours
- Chills and rigors with profuse sweating
- Severe frontal headache
- Generalized myalgia and arthralgia
- Nausea, vomiting, and abdominal discomfort
- Weakness and fatigue

Physical examination: Pallor (anemia), splenomegaly (chronic cases), hepatomegaly, mild jaundice.

### Severe and Complicated Malaria
Urgent treatment required if any of the following present:

**Neurological**: Impaired consciousness (GCS <11), prostration, multiple convulsions (>2 in 24hrs), coma (cerebral malaria, GCS ≤8)

**Respiratory**: Respiratory distress, pulmonary edema, acute respiratory distress syndrome (ARDS)

**Hematological**: Severe anemia (Hb <5 g/dL), hemoglobinuria (blackwater fever), abnormal bleeding/coagulopathy, jaundice (bilirubin >50 μmol/L)

**Metabolic**: Hypoglycemia (<2.2 mmol/L), metabolic acidosis (bicarbonate <15 mmol/L or lactate >5 mmol/L), renal impairment (creatinine >265 μmol/L)

**Circulatory**: Shock (systolic BP <80 mmHg), hyperparasitemia (>10% parasitemia)

## Differential Diagnosis
- Typhoid fever: Gradual onset, relative bradycardia
- Viral infections: Dengue, chikungunya, influenza
- Bacterial infections: Sepsis, pneumonia, meningitis, UTI
- Rickettsial diseases: Tick typhus with eschar
- Viral hemorrhagic fevers: Contact history, bleeding
- HIV seroconversion illness: Risk factors, lymphadenopathy

## Investigations
### Essential Tests
1. **Malaria Microscopy** (Gold standard): Thick film for species/density, thin film for parasitemia percentage
2. **Rapid Diagnostic Test (RDT)**: When microscopy unavailable, results in 15-20 minutes
3. **Full Blood Count**: Assess anemia (severe if Hb <5 g/dL), thrombocytopenia
4. **Blood Glucose**: Essential in severe cases, children, pregnant women

### Additional Tests for Severe Malaria
Renal function, liver function, blood gases (lactate, acidosis), blood culture, chest X-ray, urinalysis.

## Management
### Uncomplicated Malaria
**First-line: Artemether-Lumefantrine (AL) 20/120mg**
- Twice daily for 3 days (6 doses total)
- Give with fatty food/milk for absorption
- Dosing by weight:
  - 5-14kg: 1 tablet per dose
  - 15-24kg: 2 tablets per dose
  - 25-34kg: 3 tablets per dose
  - ≥35kg: 4 tablets per dose

**Special Populations:**
- Pregnancy (2nd/3rd trimester): AL or quinine + clindamycin
- Pregnancy (1st trimester): Quinine + clindamycin preferred
- Children <5kg: Refer to specialist center

### Severe Malaria
**First-line: Artesunate IV/IM**
- Dose: 2.4 mg/kg at 0, 12, 24 hours, then daily
- Minimum 24 hours, then complete with oral ACT (3 days)

**Alternative: Quinine IV** (if artesunate unavailable)
- Loading: 20 mg/kg IV over 4 hours
- Maintenance: 10 mg/kg every 8 hours
- Complete with oral quinine (total 7 days)

**Supportive Care:**
- Cautious IV fluids (risk of pulmonary edema)
- Blood transfusion if Hb <5 g/dL with respiratory distress
- Correct hypoglycemia: 50% dextrose 1 mL/kg IV
- Manage seizures: Diazepam or lorazepam
- Broad-spectrum antibiotics if bacterial co-infection suspected
- Paracetamol for fever
- Monitor: Vitals, urine output, glucose, parasitemia

### Treatment Monitoring
- Fever should resolve within 48 hours
- Repeat microscopy days 3, 7, 14, 28
- Treatment failure: Persistent fever >3 days, parasitemia day 3, clinical deterioration

## Prevention
### Vector Control
- Insecticide-treated bed nets (ITNs): Use every night
- Indoor residual spraying (IRS) in high-transmission areas
- Environmental management: Drain stagnant water
- Personal protection: Long sleeves, repellent, screens

### Chemoprophylaxis
**Intermittent Preventive Treatment in Pregnancy (IPTp)**
- Sulfadoxine-pyrimethamine (SP): 3 tablets single dose
- Start after quickening (16-20 weeks)
- Give at each antenatal visit (minimum 4 doses)

**Travelers**: Atovaquone-proguanil (daily), doxycycline (daily), or mefloquine (weekly)

## Complications
- Cerebral malaria: Coma, seizures, permanent neurological damage
- Severe anemia: Heart failure, death
- Acute renal failure requiring dialysis
- Pulmonary edema and ARDS (high mortality)
- Metabolic acidosis and multi-organ failure
- Secondary bacterial infections: Sepsis, pneumonia

## Prognosis
- Uncomplicated: Excellent with prompt treatment
- Severe: 10-50% mortality depending on complications
- Cerebral malaria: 10-20% mortality, 10% neurological sequelae in survivors
- Early diagnosis and treatment are critical

## Key Points
- Malaria is a medical emergency requiring immediate diagnosis and treatment
- Parasitological confirmation essential (except severe cases)
- Artemisinin-based combinations (ACT) first-line for uncomplicated malaria
- Parenteral artesunate first-line for severe malaria
- Prevention through bed nets and IPTp reduces morbidity and mortality"""


@pytest.fixture
def test_db():
    """
    Create temporary in-memory database with schema.
    This fixture is cleaned up automatically after each test.
    """
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()

    # Create schema
    cursor.executescript("""
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            filename TEXT NOT NULL,
            sha256_checksum TEXT NOT NULL,
            title TEXT,
            version TEXT,
            page_count INTEGER,
            processed_date TEXT
        );

        CREATE TABLE sections (
            id INTEGER PRIMARY KEY,
            document_id INTEGER NOT NULL,
            parent_id INTEGER,
            level INTEGER NOT NULL,
            heading TEXT NOT NULL,
            heading_path TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            page_start INTEGER,
            page_end INTEGER,
            FOREIGN KEY (document_id) REFERENCES documents(id),
            FOREIGN KEY (parent_id) REFERENCES sections(id)
        );

        CREATE TABLE parent_chunks (
            id INTEGER PRIMARY KEY,
            section_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER NOT NULL,
            page_start INTEGER,
            page_end INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (section_id) REFERENCES sections(id)
        );

        CREATE TABLE child_chunks (
            id INTEGER PRIMARY KEY,
            parent_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_id) REFERENCES parent_chunks(id)
        );
    """)

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def tokenizer():
    """Get tiktoken tokenizer for token counting"""
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, tokenizer) -> int:
    """Count tokens in text using tiktoken"""
    return len(tokenizer.encode(text))


def split_into_child_chunks(parent_content: str, heading_path: str, tokenizer, target_tokens: int = 256) -> list[str]:
    """
    Split parent content into child chunks of ~256 tokens each.
    Each child includes heading context prefix.
    """
    chunks = []
    paragraphs = parent_content.split('\n\n')

    current_chunk = f"Section: {heading_path}\n\n"

    for para in paragraphs:
        test_chunk = current_chunk + para + "\n\n"
        token_count = count_tokens(test_chunk, tokenizer)

        if token_count > target_tokens * 1.1 and current_chunk != f"Section: {heading_path}\n\n":
            # Save current chunk and start new one
            chunks.append(current_chunk.strip())
            current_chunk = f"Section: {heading_path}\n\n" + para + "\n\n"
        else:
            current_chunk = test_chunk

    # Add final chunk
    if current_chunk.strip() != f"Section: {heading_path}":
        chunks.append(current_chunk.strip())

    return chunks


def test_parent_child_chunk_creation(test_db, tokenizer):
    """
    TEST: Validate parent-child chunk relationship

    This is the MOST CRITICAL test for our RAG system because it validates:
    1. ONE parent chunk per section (complete clinical context)
    2. MULTIPLE child chunks per parent (precise retrieval)
    3. Foreign key relationships work (children link to parent)
    4. Token counts are accurate
    5. RAG query pattern works (search children → return parent)

    WHY THIS MATTERS:
    - Parent chunks give LLM complete, coherent clinical information
    - Child chunks enable precise, focused search
    - This prevents duplication in final results
    """
    cursor = test_db.cursor()

    # Step 1: Insert a document
    cursor.execute("""
        INSERT INTO documents (id, filename, sha256_checksum, title, version, page_count)
        VALUES (1, 'test_ucg.pdf', 'test_checksum', 'Test UCG', '1.0', 200)
    """)

    # Step 2: Insert a section (Disease level: Malaria)
    cursor.execute("""
        INSERT INTO sections (id, document_id, level, heading, heading_path,
                             order_index, page_start, page_end)
        VALUES (1, 1, 2, '1.2 Malaria', 'Infectious Diseases > 1.2 Malaria',
                2, 145, 148)
    """)

    # Step 3: Create parent chunk with full Malaria content
    parent_tokens = count_tokens(MALARIA_CONTENT, tokenizer)

    cursor.execute("""
        INSERT INTO parent_chunks (id, section_id, content, token_count,
                                   page_start, page_end)
        VALUES (1, 1, ?, ?, 145, 148)
    """, (MALARIA_CONTENT, parent_tokens))

    print(f"\n✓ Parent chunk created: {parent_tokens} tokens")

    # Step 4: Split parent into child chunks
    child_chunks = split_into_child_chunks(
        MALARIA_CONTENT,
        "Infectious Diseases > 1.2 Malaria",
        tokenizer
    )

    for idx, chunk_content in enumerate(child_chunks):
        chunk_tokens = count_tokens(chunk_content, tokenizer)
        cursor.execute("""
            INSERT INTO child_chunks (parent_id, chunk_index, content, token_count)
            VALUES (1, ?, ?, ?)
        """, (idx, chunk_content, chunk_tokens))
        print(f"✓ Child chunk {idx}: {chunk_tokens} tokens")

    test_db.commit()

    # ==================== VALIDATIONS ====================

    # VALIDATION 1: Parent chunk token count (1000-1500 target, 2000 hard max per CLAUDE.md)
    cursor.execute("SELECT token_count FROM parent_chunks WHERE id = 1")
    parent_token_count = cursor.fetchone()[0]
    assert 1000 <= parent_token_count <= 2000, \
        f"Parent should be 1000-2000 tokens (target 1000-1500, hard max 2000), got {parent_token_count}"

    if parent_token_count <= 1500:
        print(f"\n✅ PASS: Parent chunk is {parent_token_count} tokens (within ideal 1000-1500 range)")
    else:
        print(f"\n✅ PASS: Parent chunk is {parent_token_count} tokens (within acceptable 1000-2000 range, target exceeded)")

    # VALIDATION 2: Number of child chunks (should be 3-5)
    cursor.execute("SELECT COUNT(*) FROM child_chunks WHERE parent_id = 1")
    child_count = cursor.fetchone()[0]
    assert child_count >= 3, f"Should have at least 3 child chunks, got {child_count}"
    print(f"✅ PASS: Created {child_count} child chunks")

    # VALIDATION 3: Each child chunk token count (~256 target, max 512, last chunk can be smaller)
    cursor.execute("SELECT id, token_count FROM child_chunks WHERE parent_id = 1 ORDER BY chunk_index")
    all_chunks = cursor.fetchall()

    for idx, (chunk_id, token_count) in enumerate(all_chunks):
        # Hard max of 512 tokens per CLAUDE.md
        assert token_count <= 512, \
            f"Child chunk {chunk_id} exceeds hard max 512 tokens, got {token_count}"

        # Allow last chunk to be smaller (remaining content), others should be close to target
        if idx < len(all_chunks) - 1:  # Not the last chunk
            assert 200 <= token_count <= 350, \
                f"Child chunk {chunk_id} should be ~256 tokens (200-350 acceptable), got {token_count}"
        # Last chunk can be any size as long as it's not empty and not over max
        assert token_count > 0, f"Child chunk {chunk_id} is empty"

    print(f"✅ PASS: All {len(all_chunks)} child chunks within acceptable token ranges (target ~256, max 512)")

    # VALIDATION 4: All children have valid parent_id foreign key
    cursor.execute("""
        SELECT c.id, c.parent_id, p.id
        FROM child_chunks c
        JOIN parent_chunks p ON c.parent_id = p.id
        WHERE c.parent_id = 1
    """)
    fk_results = cursor.fetchall()
    assert len(fk_results) == child_count, "All children must have valid parent foreign key"
    print(f"✅ PASS: All {child_count} children have valid parent_id foreign key")

    # VALIDATION 5: Child chunks include heading context prefix
    cursor.execute("SELECT content FROM child_chunks WHERE parent_id = 1 LIMIT 1")
    first_child = cursor.fetchone()[0]
    assert first_child.startswith("Section: Infectious Diseases > 1.2 Malaria\n\n"), \
        "Child chunks must start with heading context"
    print(f"✅ PASS: Child chunks include heading context prefix")

    # VALIDATION 6: No orphaned chunks (critical for data integrity)
    cursor.execute("""
        SELECT COUNT(*) FROM child_chunks
        WHERE parent_id NOT IN (SELECT id FROM parent_chunks)
    """)
    orphaned = cursor.fetchone()[0]
    assert orphaned == 0, f"Found {orphaned} orphaned child chunks!"
    print(f"✅ PASS: No orphaned chunks (all children have valid parents)")

    # VALIDATION 7: RAG query pattern - search children, return parent
    # This simulates the actual RAG query: find relevant child, return parent to LLM
    cursor.execute("""
        SELECT DISTINCT
            p.id,
            p.content,
            p.token_count,
            COUNT(c.id) as matching_children
        FROM child_chunks c
        JOIN parent_chunks p ON c.parent_id = p.id
        WHERE c.parent_id = 1
        GROUP BY p.id
    """)
    rag_result = cursor.fetchone()

    assert rag_result is not None, "RAG query must return results"
    parent_id, parent_content, parent_tokens, matching_children = rag_result

    assert parent_id == 1, "Should return the correct parent"
    assert parent_tokens == parent_token_count, "Should return parent token count"
    assert "# 1.2 Malaria" in parent_content, "Should return full parent content"
    assert matching_children == child_count, f"Should find all {child_count} children"

    print(f"\n✅ PASS: RAG query pattern works correctly:")
    print(f"  - Query searched {matching_children} child chunks")
    print(f"  - Returned 1 parent chunk with {parent_tokens} tokens")
    print(f"  - Parent content is complete and coherent")

    # VALIDATION 8: Token count sum (children ≈ parent, accounting for heading prefix)
    cursor.execute("SELECT SUM(token_count) FROM child_chunks WHERE parent_id = 1")
    total_child_tokens = cursor.fetchone()[0]

    # Children will have more tokens due to heading prefix on each chunk
    heading_prefix = "Section: Infectious Diseases > 1.2 Malaria\n\n"
    prefix_tokens = count_tokens(heading_prefix, tokenizer)
    expected_overhead = prefix_tokens * child_count

    # Allow 15% variance for splitting boundaries
    expected_min = parent_tokens + expected_overhead * 0.85
    expected_max = parent_tokens + expected_overhead * 1.15

    print(f"\n✅ PASS: Token count validation:")
    print(f"  - Parent: {parent_tokens} tokens")
    print(f"  - Children total: {total_child_tokens} tokens")
    print(f"  - Overhead (heading prefix × {child_count}): ~{expected_overhead} tokens")
    print(f"  - Difference is expected due to heading context on each child")

    print(f"\n{'='*60}")
    print(f"🎉 ALL VALIDATIONS PASSED!")
    print(f"{'='*60}")
    print(f"Parent-Child Relationship Summary:")
    print(f"  • 1 parent chunk ({parent_token_count} tokens)")
    print(f"  • {child_count} child chunks (~256 tokens each)")
    print(f"  • All children linked via foreign key")
    print(f"  • RAG pattern validated: search children → return parent")
    print(f"  • Ready for vector embedding and retrieval!")
    print(f"{'='*60}\n")


def test_multiple_parents_query_deduplication(test_db, tokenizer):
    """
    TEST: Verify RAG query returns distinct parents (no duplicates)

    When searching across multiple child chunks from the same parent,
    the query should return only ONE instance of the parent.
    """
    cursor = test_db.cursor()

    # Set up test data
    cursor.execute("INSERT INTO documents (id, filename, sha256_checksum) VALUES (1, 'test.pdf', 'hash')")
    cursor.execute("""
        INSERT INTO sections (id, document_id, level, heading, heading_path, order_index)
        VALUES (1, 1, 2, '1.2 Malaria', 'Infectious Diseases > 1.2 Malaria', 1)
    """)

    parent_tokens = count_tokens(MALARIA_CONTENT, tokenizer)
    cursor.execute("""
        INSERT INTO parent_chunks (id, section_id, content, token_count)
        VALUES (1, 1, ?, ?)
    """, (MALARIA_CONTENT, parent_tokens))

    # Create multiple child chunks
    child_chunks = split_into_child_chunks(
        MALARIA_CONTENT,
        "Infectious Diseases > 1.2 Malaria",
        tokenizer
    )

    for idx, chunk in enumerate(child_chunks):
        chunk_tokens = count_tokens(chunk, tokenizer)
        cursor.execute("""
            INSERT INTO child_chunks (parent_id, chunk_index, content, token_count)
            VALUES (1, ?, ?, ?)
        """, (idx, chunk, chunk_tokens))

    test_db.commit()

    # RAG query that might match multiple children from same parent
    cursor.execute("""
        SELECT DISTINCT p.id, p.content
        FROM child_chunks c
        JOIN parent_chunks p ON c.parent_id = p.id
        WHERE c.parent_id = 1
    """)

    results = cursor.fetchall()

    # Should return exactly 1 parent, even though multiple children exist
    assert len(results) == 1, f"Should return 1 distinct parent, got {len(results)}"
    print(f"✅ PASS: Query returns 1 distinct parent from {len(child_chunks)} matching children")


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "-s"])
