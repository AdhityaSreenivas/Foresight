from core.ml.precursor import PRECURSOR_RULES


def extract_evidence(text, detected_precursors):

    evidence = []

    sentences = [
        sentence.strip()
        for sentence in text.replace("\n", " ").split(".")
        if sentence.strip()
    ]

    for precursor in detected_precursors:

        precursor_id = precursor["id"]

        rules = PRECURSOR_RULES.get(
            precursor_id,
            {}
        )

        keywords = rules.get(
            "keywords",
            []
        )

        matched_sentences = []

        for sentence in sentences:

            sentence_lower = sentence.lower()

            for keyword in keywords:

                if keyword.lower() in sentence_lower:

                    matched_sentences.append(
                        sentence
                    )

                    break

        evidence.append({
            "precursor": precursor["name"],
            "evidence": matched_sentences
        })

    return evidence