import argparse
import sys
from pathlib import Path

# Add project root to Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from pipelines.explainability_pipeline import ExplainabilityPipeline  # noqa: E402
from shared.config_loader import load_config  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Run the SHAP Explainability Pipeline.")
    parser.add_argument("--sample_size", type=int, default=10, help="Number of transactions to explain (default: 10, keep small for speed)")
    args = parser.parse_args()

    # Load configuration
    try:
        config = load_config("configs/model.yaml")
    except Exception as e:
        print(f"Failed to load config: {e}. Using empty config.")
        config = {}

    config["sample_size"] = args.sample_size

    # Run Pipeline
    pipeline = ExplainabilityPipeline(config=config)
    result = pipeline.run()

    if result.status == "success":
        print("\n✅ Explainability Pipeline completed successfully!")
        print(f"Explanations saved to: {result.artifacts.get('explanations_file')}")
        print("\nExample output for a single transaction:")

        # Try to print an example
        try:
            import json

            explanations_file = result.artifacts.get("explanations_file")
            if explanations_file is None:
                raise ValueError("Explanation file path is missing")

            with open(str(explanations_file)) as f:
                explanations = json.load(f)
                first_key = list(explanations.keys())[0]
                print(f"\nTransaction ID: {first_key}")
                for reason in explanations[first_key]["reasons"]:
                    print(f"  - {reason}")
        except Exception as e:
            print(f"Could not load example: {e}")

    else:
        print("\n❌ Explainability Pipeline failed.")
        print(f"Error: {result.error}")


if __name__ == "__main__":
    main()
