import argparse

from src.pipeline.step0_registration import run as run_step0
from src.pipeline.step1_parsing import run as run_step1
from src.pipeline.step2_segmentation import run as run_step2
from src.pipeline.step3_cleanup import run as run_step3
from src.pipeline.step4_tables import run as run_step4
from src.pipeline.step5_chunking import run as run_step5
from src.pipeline.step6_embeddings import run as run_step6
from src.pipeline.step7_qa import run as run_step7
from src.pipeline.step8_export import run as run_step8


def main():
    parser = argparse.ArgumentParser(description="UCG-23 ETL Pipeline")
    parser.add_argument("--step", type=int, help="Run a specific step 0–8")
    parser.add_argument("--all", action="store_true", help="Run all steps in order")
    args = parser.parse_args()

    if args.step is not None:
        steps = {
            0: run_step0,
            1: run_step1,
            2: run_step2,
            3: run_step3,
            4: run_step4,
            5: run_step5,
            6: run_step6,
            7: run_step7,
            8: run_step8,
        }
        if args.step in steps:
            print(f"Running step {args.step}…")
            steps[args.step]()
        else:
            print("Invalid step. Must be 0–8.")
        return

    if args.all:
        for i, step_fn in enumerate([
            run_step0, run_step1, run_step2,
            run_step3, run_step4, run_step5,
            run_step6, run_step7, run_step8
        ]):
            print(f"\n=== Running Step {i} ===")
            step_fn()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
