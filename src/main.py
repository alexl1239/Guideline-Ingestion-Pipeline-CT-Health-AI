"""
UCG-23 RAG ETL Pipeline Main Entry Point

Provides CLI interface for running individual pipeline steps or the full pipeline.
Initializes logging on startup and coordinates execution of all 9 steps.
"""

import argparse
import sys

from src.utils.logging_config import setup_logger, get_logger
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
    """
    Main entry point for UCG-23 ETL Pipeline.

    Initializes logging and coordinates pipeline execution based on CLI arguments.
    """
    # Initialize logging once at startup
    setup_logger()
    logger = get_logger("main")

    logger.info("=" * 80)
    logger.info("UCG-23 RAG ETL Pipeline")
    logger.info("=" * 80)

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
            logger.info(f"Running step {args.step}...")
            try:
                steps[args.step]()
                logger.success(f"Step {args.step} completed successfully")
            except Exception as e:
                logger.error(f"Step {args.step} failed: {e}")
                logger.exception("Full traceback:")
                sys.exit(1)
        else:
            logger.error("Invalid step. Must be 0–8.")
            parser.print_help()
            sys.exit(1)
        return

    if args.all:
        logger.info("Running full pipeline (steps 0-8)")
        for i, step_fn in enumerate([
            run_step0, run_step1, run_step2,
            run_step3, run_step4, run_step5,
            run_step6, run_step7, run_step8
        ]):
            logger.info("")
            logger.info("=" * 80)
            logger.info(f"STEP {i}")
            logger.info("=" * 80)
            try:
                step_fn()
                logger.success(f"Step {i} completed successfully")
            except Exception as e:
                logger.error(f"Step {i} failed: {e}")
                logger.exception("Full traceback:")
                logger.error("Pipeline aborted due to error")
                sys.exit(1)

        logger.info("")
        logger.info("=" * 80)
        logger.success("PIPELINE COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
