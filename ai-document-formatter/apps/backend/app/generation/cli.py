import argparse
import json
import logging
import os
import sys

from app.extraction.docx_extractor import DocxExtractor
from app.generation.docx_generator import DocxGenerator
from app.ir.validator import DocumentIRValidator
from app.mapping.mapper import ContentTemplateMapper
from app.semantics.classifier import SemanticClassifier
from app.templates.models import TemplateProfile
from app.templates.template_extractor import TemplateExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def generate_document_cli(
    source_path: str,
    template_path: str,
    output_docx_path: str,
    output_manifest_path: Optional[str] = None,
) -> int:
    """Run end-to-end pipeline from source and template DOCX to generated DOCX."""
    print("=" * 70)
    print("FORMATTO DETERMINISTIC DOCX GENERATOR")
    print(f"Source:   {source_path}")
    print(f"Template: {template_path}")
    print(f"Output:   {output_docx_path}")
    print("=" * 70)

    if not os.path.exists(source_path):
        print(f"ERROR: Source file does not exist: {source_path}", file=sys.stderr)
        return 1
    if not os.path.exists(template_path):
        print(f"ERROR: Template file does not exist: {template_path}", file=sys.stderr)
        return 1

    try:
        # Step 1: Extract source elements
        print("\n[1/6] Extracting source document elements...")
        extractor = DocxExtractor(source_path)
        source_elements = extractor.extract()
        print(f"      Extracted {len(source_elements)} source elements.")

        # Step 2: Semantic analysis
        print("\n[2/6] Performing semantic analysis...")
        classifier = SemanticClassifier()
        enriched_result = classifier.analyze_document(source_elements)
        enriched_elements = enriched_result.elements
        print(f"      Classified {len(enriched_elements)} enriched semantic elements.")

        # Step 3: Extract template profile and constraints
        print("\n[3/6] Extracting template constraints and styles...")
        tmpl_extractor = TemplateExtractor(template_path)
        tmpl_dict = tmpl_extractor.extract_template()
        template_profile = TemplateProfile(**tmpl_dict)
        print(f"      Extracted {len(template_profile.constraints)} constraints, {len(template_profile.styles)} styles.")

        # Step 4: Map source to template
        print("\n[4/6] Mapping source elements to template styles...")
        mapper = ContentTemplateMapper(template_profile)
        mapping_result = mapper.map_document(enriched_elements)
        print(f"      Mapping: {mapping_result.accepted_count} accepted, {mapping_result.fallback_count} fallbacks.")

        # Step 5: Build and validate Document IR
        print("\n[5/6] Building and validating Document IR...")
        doc_ir = mapping_result.to_document_ir()
        ir_validator = DocumentIRValidator()
        ir_report = ir_validator.validate(doc_ir)
        if not ir_report.is_valid:
            print(f"ERROR: Document IR validation failed with {len(ir_report.issues)} issues:", file=sys.stderr)
            for iss in ir_report.issues:
                print(f"  - {iss}", file=sys.stderr)
            return 2
        print(f"      Document IR valid: {ir_report.total_elements} elements, {ir_report.traceable_elements} traceable.")

        # Step 6: Generate DOCX
        print("\n[6/6] Generating deterministic output DOCX...")
        generator = DocxGenerator(template_path=template_path, source_docx_path=source_path)
        gen_result = generator.generate(doc_ir, output_path=output_docx_path)
        print(f"      Successfully generated: {output_docx_path}")
        print(f"      Generated {gen_result.generated_elements}/{gen_result.total_elements} elements.")

        if output_manifest_path:
            with open(output_manifest_path, "w", encoding="utf-8") as mf:
                json.dump(gen_result.manifest.model_dump(), mf, indent=2)
            print(f"      Traceability manifest saved to: {output_manifest_path}")

        print("\nSUCCESS: End-to-end DOCX generation completed successfully.")
        return 0

    except Exception as e:
        logger.exception("DOCX generation failed")
        print(f"\nFATAL ERROR: {e}", file=sys.stderr)
        return 3


def main():
    parser = argparse.ArgumentParser(description="Formatto Deterministic DOCX Generator CLI")
    parser.add_argument("--source", "-s", required=True, help="Path to input source DOCX file")
    parser.add_argument("--template", "-t", required=True, help="Path to reference template DOCX file")
    parser.add_argument("--output", "-o", required=True, help="Path for generated output DOCX file")
    parser.add_argument("--manifest", "-m", default=None, help="Optional path to save GenerationManifest JSON")
    args = parser.parse_args()

    exit_code = generate_document_cli(
        source_path=args.source,
        template_path=args.template,
        output_docx_path=args.output,
        output_manifest_path=args.manifest,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
