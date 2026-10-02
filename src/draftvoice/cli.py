import argparse
import sys

from draftvoice import __version__, learning
from draftvoice.model import FABRICATIONS, DishonestStub, ModelError, get_drafter, load_env
from draftvoice.models import Proposal
from draftvoice.pipeline import post_from_text, propose
from draftvoice.store import DataError, Founder, load_fixtures

DRAFTERS = ["env", "stub", "gemini"] + [f"dishonest-{k}" for k in FABRICATIONS]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="draftvoice",
        description="Decide whether to comment on a post, and draft one in the founder's voice.",
    )
    parser.add_argument("--version", action="version", version=f"draftvoice {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="command")

    p = commands.add_parser("propose", help="propose a comment for one post, or do nothing")
    p.add_argument("--founder", required=True, help="rico, fathin, or the synthetic alex")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="the post text, pasted by you")
    source.add_argument("--post", help="a synthetic fixture post id, e.g. p-agents")
    p.add_argument(
        "--drafter", choices=DRAFTERS, default="env",
        help="who writes the draft: env (MODEL_MODE in .env, default stub), stub, gemini, "
             "or a dishonest stub that lies on purpose",
    )
    r = commands.add_parser("review", help="accept, edit, reject, or skip a proposal")
    r.add_argument("proposal", help="the proposal id printed by propose, e.g. pr-1a2b3c4d")
    action = r.add_mutually_exclusive_group(required=True)
    action.add_argument("--accept", action="store_true", help="use the draft as it is")
    action.add_argument("--edit", metavar="TEXT", help="use your edited version instead")
    action.add_argument("--reject", action="store_true", help="the draft is wrong")
    action.add_argument("--skip", action="store_true", help="not commenting on this post")

    ru = commands.add_parser("rules", help="list, approve, reject, or revert learned voice rules")
    ru.add_argument("action", nargs="?", default="list", choices=["list", "approve", "reject", "revert"])
    ru.add_argument("target", nargs="?", help="a rule id for approve/reject")
    ru.add_argument("--founder", help="whose rules (needed for revert)")

    sv = commands.add_parser("serve", help="run the local API and the mock feed at http://127.0.0.1:8765")
    sv.add_argument("--port", type=int, default=8765)

    e = commands.add_parser("eval", help="run every check on the fixtures and write docs/eval-report.md")
    e.add_argument("--out", help="where to write the report (default docs/eval-report.md)")
    e.add_argument("--live", action="store_true", help="also judge live Gemini drafts (needs GEMINI_API_KEY)")
    return parser


def cmd_eval(args) -> int:
    from pathlib import Path

    from draftvoice import eval as evaluation

    live = _drafter("gemini") if args.live else None
    report = evaluation.run(live)
    path = evaluation.write(report, Path(args.out) if args.out else evaluation.REPORT)
    text = path.read_text()
    summary = text[text.index("| What we measured"):text.index("The 95% range")]
    print(summary.strip())
    print(f"\nreport: {path}")
    return 0 if report.ok else 1


def _drafter(name: str):
    if name.startswith("dishonest-"):
        return DishonestStub(name.removeprefix("dishonest-"))
    env = load_env()
    if name != "env":
        env["MODEL_MODE"] = name
    return get_drafter(env)


def render(proposal: Proposal, founder: Founder, post_text: str) -> str:
    name = founder.profile.display_name
    preview = post_text if len(post_text) <= 90 else post_text[:87] + "..."
    lines = [f"{name} · post: \"{preview}\"", ""]
    if proposal.decision == "do_nothing":
        lines.append(f"DO NOTHING  {proposal.reason}")
    else:
        evidence = {e.id: e for e in founder.evidence}
        lines.append("DRAFT")
        for s in proposal.sentences:
            lines.append(f"  {s.text}   [{', '.join(s.evidence_ids)}]")
        lines.append("")
        lines.append("EVIDENCE")
        for i in dict.fromkeys(i for s in proposal.sentences for i in s.evidence_ids):
            lines.append(f"  {i}  {evidence[i].text}  ({evidence[i].source})")
    if proposal.checks:
        blocking = [c for c in proposal.checks if c.blocking]
        lines.append("")
        lines.append("CHECKS  " + "  ".join(f"{c.check.split()[0]} {'✓' if c.passed else '✗'}" for c in blocking))
        for c in blocking:
            if not c.passed:
                lines.append(f"  ✗ {c.check}: {c.detail}")
        for c in proposal.checks:
            if not c.blocking and not c.passed:
                lines.append(f"  ⚠ {c.check}: {c.detail}")
    lines.append("")
    lines.append("Nothing was posted. Copy the draft and post it yourself." if proposal.decision == "draft"
                 else "Nothing was posted.")
    return "\n".join(lines)


def cmd_propose(args) -> int:
    founder = learning.current_founder(args.founder)
    if args.post:
        fixtures = {f.post.id: f.post for f in load_fixtures()}
        if args.post not in fixtures:
            raise DataError(f"unknown fixture post '{args.post}' (known: {', '.join(fixtures)})")
        post = fixtures[args.post]
    else:
        post = post_from_text(args.text)
    proposal = propose(post, founder, _drafter(args.drafter))
    learning.save_proposal(proposal, post.text)
    print(render(proposal, founder, post.text))
    if proposal.decision == "draft":
        print(f"\nReview it: draftvoice review {proposal.id} --accept | --edit \"...\" | --reject | --skip")
    return 0


def cmd_serve(args) -> int:
    from draftvoice.api import serve

    server = serve(args.port)
    print(f"DraftVoice is running at http://127.0.0.1:{args.port}  (mock feed; Ctrl+C to stop)")
    print("Only this machine can reach it. Nothing is ever posted.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


def cmd_review(args) -> int:
    action = "accept" if args.accept else "edit" if args.edit else "reject" if args.reject else "skip"
    rv, suggestion = learning.review(args.proposal, action, args.edit)
    print(f"Saved: {action} ({rv.id}).")
    if action in ("accept", "edit"):
        text = args.edit if action == "edit" else learning.draft_text(learning.get_proposal(args.proposal))
        print(f"\nReady to copy (DraftVoice never posts):\n  {text}")
    if suggestion:
        print(f"\nYou made this change twice. Suggested rule ({suggestion.id}): {suggestion.rule}")
        print(f"Apply it: draftvoice rules approve {suggestion.id}   Ignore it: draftvoice rules reject {suggestion.id}")
    return 0


def cmd_rules(args) -> int:
    if args.action == "approve":
        version = learning.approve(_need(args.target, "a rule id"))
        print(f"Approved. Profile is now version {version}. Undo: draftvoice rules revert --founder "
              f"{learning._get_rule(args.target).founder_id}")
    elif args.action == "reject":
        learning.reject(_need(args.target, "a rule id"))
        print("Rejected. Nothing changed.")
    elif args.action == "revert":
        version = learning.revert(_need(args.founder, "--founder"))
        print(f"Reverted. {args.founder} is back on profile version {version}.")
    else:
        rules = learning.rule_proposals(args.founder)
        if not rules:
            print("No rule suggestions yet. One edit never makes a rule; the same change twice suggests one.")
        for r in rules:
            made = f", created v{r.profile_version}" if r.profile_version else ""
            print(f"{r.id}  {r.founder_id:<7} {r.status:<9} {r.rule}  (from {len(r.source_review_ids)} edits{made})")
        for fid in sorted({r.founder_id for r in rules}):
            active, all_versions = learning.versions(fid)
            print(f"{fid}: active profile v{active} of {all_versions}")
    return 0


def _need(value, what):
    if not value:
        raise learning.ReviewError(f"this needs {what}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        handler = {"eval": cmd_eval, "review": cmd_review, "rules": cmd_rules, "serve": cmd_serve}.get(args.command, cmd_propose)
        return handler(args)
    except (DataError, ModelError, learning.ReviewError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
