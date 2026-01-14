# Main.py
# M365 Copilot — Orchestration entrypoint
# Loads config, runs grader/report/record pipelines, and sends outputs via EmailClient.

import os
import sys
import json
import argparse
import logging
import datetime
from typing import Dict, Any, List, Optional

# Import your provided Email.py
from Email import EmailClient, build_html_template

# Optional project modules — handle if missing gracefully
try:
    import grader
except ImportError:
    grader = None

try:
    import report
except ImportError:
    report = None

try:
    import record
except ImportError:
    record = None

# Logger setup
logger = logging.getLogger("Main")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ----------------------------
# Config helpers
# ----------------------------

def load_json_config(path: Optional[str]) -> Dict[str, Any]:
    """Load a JSON config file if present."""
    cfg: Dict[str, Any] = {}
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            logger.info("Loaded config.json: %s", path)
        except Exception as e:
            logger.error("Failed to load config file %s: %s", path, e)
    return cfg


def load_env_into_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay environment variables onto config dictionary."""
    env_map = {
        # Profile / org
        "COMPANY_NAME": "COMPANY_NAME",
        "JOB_TITLE": "JOB_TITLE",
        "MANAGER": "MANAGER",
        "SKIP_MANAGER": "SKIP_MANAGER",
        "OFFICE_LOCATION": "OFFICE_LOCATION",
        "USER_NAME": "USER_NAME",
        # UI
        "UI_THEME": "UI_THEME",
        "UI_PREF": "UI_PREF",
        "TEMPLATES_DIR": "TEMPLATES_DIR",
        # Outputs
        "OUTPUT_DIR": "OUTPUT_DIR",
        "INCLUDE_PNG": "INCLUDE_PNG",
        "INCLUDE_PPTX": "INCLUDE_PPTX",
        "INCLUDE_XLSX": "INCLUDE_XLSX",
        # Email / SMTP
        "SMTP_HOST": "SMTP_HOST",
        "SMTP_PORT": "SMTP_PORT",
        "SMTP_USER": "SMTP_USER",
        "SMTP_PASS": "SMTP_PASS",
        "SMTP_SSL": "SMTP_SSL",
        "FROM_EMAIL": "FROM_EMAIL",
        "FROM_NAME": "FROM_NAME",
        "REPLY_TO": "REPLY_TO",
        "DEFAULT_RECIPIENTS": "DEFAULT_RECIPIENTS",
        "CC_LIST": "CC_LIST",
        "BCC_LIST": "BCC_LIST",
        # Project metadata
        "PROJECT_NAME": "PROJECT_NAME",
        "RUN_TAG": "RUN_TAG",
    }
    for k, env_k in env_map.items():
        v = os.getenv(env_k)
        if v is None:
            continue
        if k in {"INCLUDE_PNG", "INCLUDE_PPTX", "INCLUDE_XLSX", "SMTP_SSL"}:
            config[k] = str(v).strip().lower() in {"1", "true", "yes", "on"}
        elif k in {"SMTP_PORT"}:
            try:
                config[k] = int(v)
            except ValueError:
                logger.warning("Invalid SMTP_PORT env value: %s", v)
        elif k in {"DEFAULT_RECIPIENTS", "CC_LIST", "BCC_LIST"}:
            config[k] = [s.strip() for s in v.split(",") if s.strip()]
        else:
            config[k] = v
    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run operational pipeline (grade/report/record) and email outputs."
    )
    parser.add_argument("--config", type=str, default="config.json", help="Path to JSON config")
    parser.add_argument("--output-dir", type=str, help="Override OUTPUT_DIR")
    parser.add_argument("--include-png", action="store_true", help="Attach PNG outputs")
    parser.add_argument("--include-pptx", action="store_true", help="Attach PPTX outputs")
    parser.add_argument("--include-xlsx", action="store_true", help="Attach XLSX outputs")
    parser.add_argument("--theme", type=str, choices=["light", "dark"], help="UI theme")
    parser.add_argument("--recipients", type=str, help="Comma separated recipient emails")
    parser.add_argument("--cc", type=str, help="Comma separated CC emails")
    parser.add_argument("--bcc", type=str, help="Comma separated BCC emails")
    parser.add_argument("--run-tag", type=str, help="Run tag (e.g., Daily, Weekly, Audit-Q1)")
    parser.add_argument("--project-name", type=str, help="Project name appearing in email header")
    parser.add_argument("--templates-dir", type=str, help="Templates directory for UI/HTML")
    return parser.parse_args()


def build_config() -> Dict[str, Any]:
    args = parse_args()
    config = load_json_config(args.config)
    config = load_env_into_config(config)

    # Overlay CLI args
    if args.output_dir:
        config["OUTPUT_DIR"] = args.output_dir
    if args.include_png:
        config["INCLUDE_PNG"] = True
    if args.include_pptx:
        config["INCLUDE_PPTX"] = True
    if args.include_xlsx:
        config["INCLUDE_XLSX"] = True
    if args.theme:
        config["UI_THEME"] = args.theme
    if args.recipients:
        config["DEFAULT_RECIPIENTS"] = [s.strip() for s in args.recipients.split(",") if s.strip()]
    if args.cc:
        config["CC_LIST"] = [s.strip() for s in args.cc.split(",") if s.strip()]
    if args.bcc:
        config["BCC_LIST"] = [s.strip() for s in args.bcc.split(",") if s.strip()]
    if args.run_tag:
        config["RUN_TAG"] = args.run_tag
    if args.project_name:
        config["PROJECT_NAME"] = args.project_name
    if args.templates_dir:
        config["TEMPLATES_DIR"] = args.templates_dir

    # Defaults
    config.setdefault("COMPANY_NAME", "Comp_HPK")
    config.setdefault("JOB_TITLE", "Operational Manager")
    config.setdefault("MANAGER", "Tanveer Hussain (Comp_HPK)")
    config.setdefault("SKIP_MANAGER", "Liu Changwei 刘长伟 (690)")
    config.setdefault("OFFICE_LOCATION", "")
    config.setdefault("USER_NAME", "Khan Roy Jamshaid (Comp_HPK)")

    config.setdefault("UI_THEME", "dark")
    config.setdefault("UI_PREF", "stunning")
    config.setdefault("TEMPLATES_DIR", "./templates")

    config.setdefault("OUTPUT_DIR", "./outputs")
    config.setdefault("INCLUDE_PNG", True)
    config.setdefault("INCLUDE_PPTX", True)
    config.setdefault("INCLUDE_XLSX", True)

    # SMTP defaults (Office365 typical: host 587 STARTTLS)
    config.setdefault("SMTP_HOST", os.getenv("SMTP_HOST", "smtp.office365.com"))
    config.setdefault("SMTP_PORT", int(os.getenv("SMTP_PORT", "587")))
    config.setdefault("SMTP_USER", os.getenv("SMTP_USER"))
    config.setdefault("SMTP_PASS", os.getenv("SMTP_PASS"))
    config.setdefault("SMTP_SSL", False)  # STARTTLS by default

    config.setdefault("FROM_EMAIL", config.get("SMTP_USER"))
    config.setdefault("FROM_NAME", config.get("USER_NAME"))
    config.setdefault("REPLY_TO", config.get("FROM_EMAIL"))

    config.setdefault("DEFAULT_RECIPIENTS", [])
    config.setdefault("CC_LIST", [])
    config.setdefault("BCC_LIST", [])

    config.setdefault("PROJECT_NAME", "Operational Audit")
    config.setdefault("RUN_TAG", "Daily")

    # Ensure output directory exists
    os.makedirs(config["OUTPUT_DIR"], exist_ok=True)
    return config

# ----------------------------
# Pipeline execution
# ----------------------------

def run_grader(config: Dict[str, Any]) -> Dict[str, Any]:
    """Run grader stage and return summary dict."""
    if grader is None:
        logger.warning("grader module not found; skipping.")
        return {"score": None, "notes": "grader module not available"}
    try:
        # Expected API: grader.run(output_dir=...) -> dict
        summary = grader.run(output_dir=config["OUTPUT_DIR"])
        logger.info("Grader completed.")
        return summary or {}
    except Exception as e:
        logger.error("Grader failed: %s", e)
        return {"error": str(e)}


def run_report(config: Dict[str, Any]) -> Dict[str, Any]:
    """Run report stage; return dict incl. list of attachments."""
    if report is None:
        logger.warning("report module not found; skipping.")
        return {"attachments": []}

    attachments: List[str] = []
    results: Dict[str, Any] = {}

    try:
        # PNGs
        if config.get("INCLUDE_PNG", True) and hasattr(report, "generate_pngs"):
            pngs = report.generate_pngs(
                output_dir=config["OUTPUT_DIR"],
                theme=config["UI_THEME"],
                templates_dir=config["TEMPLATES_DIR"]
            )
            if pngs:
                attachments.extend(pngs)
            results["pngs"] = pngs

        # PPTX
        if config.get("INCLUDE_PPTX", True) and hasattr(report, "build_pptx"):
            pptx_path = report.build_pptx(
                output_dir=config["OUTPUT_DIR"],
                theme=config["UI_THEME"]
            )
            if pptx_path:
                attachments.append(pptx_path)
            results["pptx"] = pptx_path

        # XLSX
        if config.get("INCLUDE_XLSX", True) and hasattr(report, "export_xlsx"):
            xlsx_path = report.export_xlsx(output_dir=config["OUTPUT_DIR"])
            if xlsx_path:
                attachments.append(xlsx_path)
            results["xlsx"] = xlsx_path

        logger.info("Report generation completed with %d attachments.", len(attachments))
    except Exception as e:
        logger.error("Report generation failed: %s", e)
        results["error"] = str(e)

    results["attachments"] = attachments
    return results


def run_record(config: Dict[str, Any]) -> Dict[str, Any]:
    """Run record stage; return dict with KPIs/cards."""
    if record is None:
        logger.warning("record module not found; skipping.")
        return {"kpis": []}
    try:
        # Expected API: record.collect_kpis(output_dir=...) -> list of {'title','value'}
        kpis = record.collect_kpis(output_dir=config["OUTPUT_DIR"])
        return {"kpis": kpis or []}
    except Exception as e:
        logger.error("Record (KPIs) failed: %s", e)
        return {"error": str(e), "kpis": []}

# ----------------------------
# Email orchestration
# ----------------------------

def build_email_context(config: Dict[str, Any],
                        grader_summary: Dict[str, Any],
                        report_results: Dict[str, Any],
                        record_results: Dict[str, Any]) -> Dict[str, Any]:
    """Build context dict for build_html_template in Email.py."""
    date_str = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p")
    score = grader_summary.get("score")
    notes = grader_summary.get("notes")
    error_msgs: List[str] = []

    if grader_summary.get("error"):
        error_msgs.append(f"Grader Error: {grader_summary['error']}")
    if report_results.get("error"):
        error_msgs.append(f"Report Error: {report_results['error']}")
    if record_results.get("error"):
        error_msgs.append(f"Record Error: {record_results['error']}")

    summary_parts: List[str] = []
    if score is not None:
        summary_parts.append(f"Overall grade: <strong>{score}</strong>.")
    if notes:
        summary_parts.append(f"Notes: {notes}")
    if error_msgs:
        summary_parts.append("<br/>".join(error_msgs))

    summary_text = " ".join(summary_parts) if summary_parts else "Run completed successfully."

    cards = record_results.get("kpis") or []
    if not cards:
        cards = [
            {"title": "Theme", "value": config.get("UI_THEME", "dark").title()},
            {"title": "Outputs", "value": f"PNG:{config.get('INCLUDE_PNG')} PPTX:{config.get('INCLUDE_PPTX')} XLSX:{config.get('INCLUDE_XLSX')}"}
        ]

    links = [
        {"text": "Open Outputs Folder", "href": f"file://{os.path.abspath(config['OUTPUT_DIR'])}"},
    ]

    context = {
        "PROJECT_NAME": config.get("PROJECT_NAME", "Operational Audit"),
        "RUN_TAG": config.get("RUN_TAG", "Daily"),
        "UI_THEME": config.get("UI_THEME", "dark"),
        "COMPANY_NAME": config.get("COMPANY_NAME", ""),
        "USER_NAME": config.get("USER_NAME", ""),
        "JOB_TITLE": config.get("JOB_TITLE", ""),
        "MANAGER": config.get("MANAGER", ""),
        "SKIP_MANAGER": config.get("SKIP_MANAGER", ""),
        "OFFICE_LOCATION": config.get("OFFICE_LOCATION", ""),
        "SUMMARY": summary_text,
        "CARDS": cards,
        "LINKS": links,
        "DATE_STR": date_str,
    }
    return context


def send_pipeline_email(config: Dict[str, Any],
                        context: Dict[str, Any],
                        attachments: List[str]) -> None:
    """Compose and send email using EmailClient."""
    email_client = EmailClient(
        smtp_host=config["SMTP_HOST"],
        smtp_port=config["SMTP_PORT"],
        smtp_user=config.get("SMTP_USER"),
        smtp_pass=config.get("SMTP_PASS"),
        use_ssl=config.get("SMTP_SSL", False),
        from_email=config.get("FROM_EMAIL"),
        from_name=config.get("FROM_NAME"),
        default_cc=config.get("CC_LIST", []),
        default_bcc=config.get("BCC_LIST", []),
        reply_to=config.get("REPLY_TO")
    )

    subject = f"{config.get('PROJECT_NAME','Operational Audit')} • {config.get('RUN_TAG','Daily')} • {datetime.datetime.now().strftime('%Y-%m-%d')}"
    html_body = build_html_template(context)
    text_body = f"{context.get('SUMMARY','Run completed.')}\n\nOutputs: {os.path.abspath(config.get('OUTPUT_DIR','./outputs'))}"

    recipients = config.get("DEFAULT_RECIPIENTS", [])
    if not recipients:
        logger.warning("No recipients configured. Email will not be sent.")
        return

    email_client.send_report(
        to=recipients,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        cc=config.get("CC_LIST", []),
        bcc=config.get("BCC_LIST", []),
        attachments=attachments,
        inline_images={},  # Map cid -> path if needed, e.g., {"hero": "./outputs/hero.png"}
        headers={"X-Run-Tag": config.get("RUN_TAG", "Daily")}
    )

# ----------------------------
# Main entrypoint
# ----------------------------

def main():
    config = build_config()
    logger.info("Config ready. Output dir: %s", config["OUTPUT_DIR"])

    # Execute pipeline stages
    grader_summary = run_grader(config)
    report_results = run_report(config)
    record_results = run_record(config)

    # Build email context
    context = build_email_context(config, grader_summary, report_results, record_results)

    # Send email with attachments
    attachments = report_results.get("attachments", [])
    send_pipeline_email(config, context, attachments)

    logger.info("Pipeline completed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        sys.exit(1)
