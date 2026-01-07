
        def build(report: dict) -> str:
            lines = ["Audit Report", "============", f"URL: {report.get('url')}"]
            lines.append(f"Score: {report.get('score')}")
            lines.append("Issues:")
            for i in report.get('issues', []):
                lines.append(f"- {i}")
            return "
".join(lines)
