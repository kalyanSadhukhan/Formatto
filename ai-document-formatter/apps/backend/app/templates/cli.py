import argparse
import json
import os
import sys

from app.domain.schemas.data_contracts import ApiError
from app.templates.template_extractor import TemplateExtractor


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic DOCX Template Extraction CLI (Specification V2, Phase 3A)"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to reference DOCX template file"
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Path to output JSON profile file (default: stdout/summary)"
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
            message=f"Template file not found: {args.input}",
            stage="EXTRACTING_TEMPLATE",
            details={"input": args.input}
        )
        sys.stderr.write(f"Error: {err.model_dump_json()}\n")
        sys.exit(1)

    try:
        extractor = TemplateExtractor(input_path)
        profile = extractor.extract_template()
    except Exception as e:
        err = ApiError(
            error_code="CORRUPT_DOCUMENT",
            message=f"Failed to extract template: {str(e)}",
            stage="EXTRACTING_TEMPLATE",
            details={"input": args.input, "error": str(e)}
        )
        sys.stderr.write(f"Error: {err.model_dump_json()}\n")
        sys.exit(1)

    if args.output:
        out_path = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        if not args.silent:
            print(f"Template profile successfully written to {args.output}")

    if not args.silent:
        sections = profile.get("sections", [])
        styles = profile.get("styles", {})
        constraints = profile.get("constraints", [])
        num_schemes = profile.get("numbering_schemes", {})

        print("\n" + "=" * 65)
        print("          PHASE 3A TEMPLATE EXTRACTION PROFILE")
        print("=" * 65)
        print(f"Template ID:        {profile['template_id']}")
        print(f"Total Sections:     {len(sections)}")
        if sections:
            s0 = sections[0]
            print(f"  Primary Page Size: {s0['page_size_name']} ({s0['page_width_pt']} x {s0['page_height_pt']} pt)")
            print(f"  Orientation:       {s0['orientation']}")
            print(f"  Margins (pt):      Top={s0['margins_pt']['top']}, Bottom={s0['margins_pt']['bottom']}, Left={s0['margins_pt']['left']}, Right={s0['margins_pt']['right']}")
            print(f"  Page Numbering:    {'Detected in Footer/Header' if any(s['has_page_number'] for s in sections) else 'None'}")

        print(f"Total Styles:       {len(styles)}")
        headings = [s for s in styles.values() if s.get("resolved_properties", {}).get("outline_level")]
        print(f"  Heading Levels:   {len(headings)} heading styles with outline levels")
        print(f"Numbering Schemes:  {len(num_schemes)} list templates defined")
        print(f"Total Constraints:  {len(constraints)}")

        # Provenance breakdown
        prov_counts = {}
        for c in constraints:
            p = c.get("provenance", "UNKNOWN")
            prov_counts[p] = prov_counts.get(p, 0) + 1
        prov_str = ", ".join(f"{k}: {v}" for k, v in sorted(prov_counts.items()))
        print(f"  Provenance:       {prov_str}")
        print("=" * 65 + "\n")

    if not args.output and args.silent:
        print(json.dumps(profile, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
