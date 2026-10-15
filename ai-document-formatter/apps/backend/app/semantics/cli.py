import argparse
import json
import os
import sys

from app.domain.schemas.data_contracts import ApiError, SourceElement
from app.extraction.docx_extractor import DocxExtractor
from app.semantics.classifier import SemanticClassifier
from app.semantics.llm_provider import get_llm_provider


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic & LLM-Assisted Semantic Analysis CLI (Specification V2, Phase 4)"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to source DOCX file or extraction.json file"
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Path to output semantic analysis JSON file (default: stdout/summary)"
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=0.70,
        help="Ambiguity confidence threshold (default: 0.70)"
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use deterministic mock LLM provider"
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Suppress human-readable summary output"
    )

    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        err = ApiError(
            error_code="INVALID_UPLOAD",
            message=f"Input file not found: {args.input}",
            stage="ANALYZING_SOURCE",
            details={"input": args.input}
        )
        sys.stderr.write(f"Error: {err.model_dump_json()}\n")
        sys.exit(1)

    try:
        elements = []
        if input_path.endswith(".json"):
            with open(input_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            # Support list of elements or envelope
            if isinstance(raw_data, list):
                elements = [SourceElement(**item) for item in raw_data]
            elif isinstance(raw_data, dict) and "elements" in raw_data:
                elements = [SourceElement(**item) for item in raw_data["elements"]]
        else:
            extractor = DocxExtractor(input_path)
            elements = extractor.extract()

        provider = get_llm_provider(mock_mode=args.mock_llm or True)
        classifier = SemanticClassifier(
            llm_provider=provider,
            confidence_threshold=args.threshold,
        )

        result = classifier.analyze_document(elements)

    except Exception as e:
        err = ApiError(
            error_code="SEMANTIC_ANALYSIS_FAILED",
            message=f"Semantic analysis failed: {str(e)}",
            stage="ANALYZING_SOURCE",
            details={"input": args.input, "error": str(e)}
        )
        sys.stderr.write(f"Error: {err.model_dump_json()}\n")
        sys.exit(1)

    if args.output:
        out_path = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(result.model_dump_json(indent=2))
        if not args.silent:
            print(f"Semantic analysis successfully written to {args.output}")

    if not args.silent:
        print("\n" + "=" * 65)
        print("          PHASE 4 SEMANTIC ANALYSIS SUMMARY")
        print("=" * 65)
        print(f"Document ID:           {result.document_id}")
        print(f"Total Elements:        {result.total_elements}")
        print(f"Deterministic Rules:   {result.deterministic_classified_count}")
        print(f"Ambiguous Elements:    {result.ambiguous_elements_count}")
        print(f"LLM Classifications:   {result.llm_classified_count}")

        print("\nRole Breakdown:")
        for role, count in sorted(result.role_counts.items()):
            print(f"  - {role:<20}: {count}")

        print("\nClassification Methods:")
        for method, count in sorted(result.method_counts.items()):
            print(f"  - {method:<20}: {count}")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
