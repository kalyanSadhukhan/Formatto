import argparse
import json
import os
import sys

from app.domain.schemas.data_contracts import ApiError, SourceElement
from app.extraction.docx_extractor import DocxExtractor
from app.mapping.mapper import ContentTemplateMapper
from app.semantics.classifier import SemanticClassifier
from app.semantics.models import EnrichedSourceElement
from app.templates.models import TemplateProfile
from app.templates.template_extractor import TemplateExtractor


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic Source-to-Template Mapping CLI (Specification V2, Phase 5)"
    )
    parser.add_argument(
        "--source", "-s",
        required=True,
        help="Path to semantic_elements.json, extraction.json, or source DOCX"
    )
    parser.add_argument(
        "--template", "-t",
        required=True,
        help="Path to template_profile.json or template DOCX"
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Path to output mapping result JSON file"
    )
    parser.add_argument(
        "--ir-output",
        default=None,
        help="Path to output Document IR JSON file (optional)"
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Suppress human-readable summary output"
    )

    args = parser.parse_args()

    # 1. Load source elements
    src_path = os.path.abspath(args.source)
    if not os.path.exists(src_path):
        err = ApiError(
            error_code="INVALID_UPLOAD",
            message=f"Source file not found: {args.source}",
            stage="MAPPING",
            details={"source": args.source}
        )
        sys.stderr.write(f"Error: {err.model_dump_json()}\n")
        sys.exit(1)

    try:
        if src_path.endswith(".json"):
            with open(src_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "elements" in data:
                raw_elems = data["elements"]
            elif isinstance(data, list):
                raw_elems = data
            else:
                raw_elems = []
            
            # Check if elements are already EnrichedSourceElement
            if raw_elems and "semantic_role" in raw_elems[0]:
                elements = [EnrichedSourceElement(**e) for e in raw_elems]
            else:
                base_elems = [SourceElement(**e) for e in raw_elems]
                classifier = SemanticClassifier()
                res = classifier.analyze_document(base_elems)
                elements = res.elements
        else:
            extractor = DocxExtractor(src_path)
            base_elems = extractor.extract()
            classifier = SemanticClassifier()
            res = classifier.analyze_document(base_elems)
            elements = res.elements

        # 2. Load template profile
        tpl_path = os.path.abspath(args.template)
        if not os.path.exists(tpl_path):
            err = ApiError(
                error_code="INVALID_UPLOAD",
                message=f"Template file not found: {args.template}",
                stage="MAPPING",
                details={"template": args.template}
            )
            sys.stderr.write(f"Error: {err.model_dump_json()}\n")
            sys.exit(1)

        if tpl_path.endswith(".json"):
            with open(tpl_path, "r", encoding="utf-8") as f:
                tpl_data = json.load(f)
            template_profile = TemplateProfile(**tpl_data)
        else:
            ext = TemplateExtractor(tpl_path)
            tpl_dict = ext.extract_template()
            template_profile = TemplateProfile(**tpl_dict)

        # 3. Execute deterministic mapping
        mapper = ContentTemplateMapper(template_profile)
        mapping_result = mapper.map_document(elements)

    except Exception as e:
        err = ApiError(
            error_code="MAPPING_FAILED",
            message=f"Source-to-template mapping failed: {str(e)}",
            stage="MAPPING",
            details={"source": args.source, "template": args.template, "error": str(e)}
        )
        sys.stderr.write(f"Error: {err.model_dump_json()}\n")
        sys.exit(1)

    # 4. Write outputs
    if args.output:
        out_path = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(mapping_result.model_dump_json(indent=2))
        if not args.silent:
            print(f"Mapping result successfully written to {args.output}")

    if args.ir_output:
        ir = mapping_result.to_document_ir()
        ir_path = os.path.abspath(args.ir_output)
        os.makedirs(os.path.dirname(ir_path) or ".", exist_ok=True)
        with open(ir_path, "w", encoding="utf-8") as f:
            f.write(ir.model_dump_json(indent=2))
        if not args.silent:
            print(f"Document IR successfully written to {args.ir_output}")

    if not args.silent:
        print("\n" + "=" * 65)
        print("          PHASE 5 SOURCE-TO-TEMPLATE MAPPING SUMMARY")
        print("=" * 65)
        print(f"Document ID:           {mapping_result.document_id}")
        print(f"Template ID:           {mapping_result.template_id}")
        print(f"Total Elements Mapped: {mapping_result.total_elements}")
        print(f"Accepted Mappings:     {mapping_result.accepted_count}")
        print(f"Ambiguous Elements:    {mapping_result.ambiguous_count}")
        print(f"Rejected / Unsupported:{mapping_result.rejected_count}")
        print(f"Fallbacks Applied:     {mapping_result.fallback_count}")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
