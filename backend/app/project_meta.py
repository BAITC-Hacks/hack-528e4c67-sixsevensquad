"""Small project summaries, safe for history and polling."""


def summary(project):
    documents = [{"name": d["name"], "side": d["side"], "clauses": len(d["clauses"])}
                 for d in project.get("documents", [])]
    names = {side: [d["name"] for d in documents if d["side"] == side] for side in ("before", "after")}
    title = " → ".join(", ".join(names[side]) for side in ("before", "after")) or "Сравнение документов"
    result = project.get("result") or {}
    return {**{k: project.get(k) for k in ("id", "created", "status", "stage", "error", "started", "finished", "metrics", "attempts", "mode")},
            "title": title, "documents": documents,
            "counts": project.get("counts", result.get("counts", {})),
            "reviewed": sum(r.get("decision") != "pending" for r in project.get("reviews", {}).values())}
