import argparse
import sys

from draftvoice import __version__
from draftvoice.model import FABRICATIONS, DishonestStub, ModelError, get_drafter, load_env
from draftvoice.models import Proposal
from draftvoice.pipeline import post_from_text, propose
from draftvoice.store import DataError, Founder, find_founder, load_fixtures

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
    return parser


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
    founder = find_founder(args.founder)
    if args.post:
        fixtures = {f.post.id: f.post for f in load_fixtures()}
        if args.post not in fixtures:
            raise DataError(f"unknown fixture post '{args.post}' (known: {', '.join(fixtures)})")
        post = fixtures[args.post]
    else:
        post = post_from_text(args.text)
    proposal = propose(post, founder, _drafter(args.drafter))
    print(render(proposal, founder, post.text))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        return cmd_propose(args)
    except (DataError, ModelError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
