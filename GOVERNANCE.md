# How Sky City is run

Sky City is led by its creator, **Kenny Hass**, who has the final say on the game's direction, its releases and who joins the team. Day-to-day, the project runs on the roles below. Everyone starts at the top of the list, and people move down it by contributing.

## Roles

| Role | Who | What they can do |
|---|---|---|
| **Player / tester** | Anyone | Play builds, report bugs, suggest ideas |
| **Contributor** | Anyone with a merged pull request | Fork the repo and open pull requests. No permission needed. |
| **Triager** | Invited contributors | Label, sort and close issues; help newcomers |
| **Collaborator** | Invited contributors | Write access: branches, file locks, reviewing PRs in their area |
| **Maintainer** | Kenny + a small core team | Approve and merge PRs, cut releases, manage the team |

## How people move up

**Contributor → Triager:** after about **3 good pull requests** merged over at least **a month**, a maintainer may invite you. Good means focused, well described and responsive to review.

**Triager → Collaborator:** after steady contributions over **at least 3 months**, usually with an area you clearly own (traffic, landmarks, the city generator, a vehicle set). Collaborators are usually listed as code owners for that area.

**Collaborator → Maintainer:** by invitation from Kenny only, after **at least 6 months** as a collaborator and a video call with Kenny. Maintainers help run the team; publishing releases and signing builds stay with Kenny.

**What maintainers look for:**
- **Fit:** your work matches the vision and feel of the game.
- **Quality:** clean, tested changes that follow the asset rules.
- **Follow-through:** you finish what you start, or hand it off clearly.
- **Communication:** you discuss big changes before building them.
- **Asset discipline:** every asset you add has a clear, compatible licence.

Nobody is owed a role, and an invitation can be declined. Roles exist to make the work go smoothly, not as rank.

## Trust and security

Trust is earned in small steps, and no single step gives anyone control of the project. We do this on purpose: in 2024 an attacker spent two years earning maintainer rights on the *xz-utils* compression library, then hid a backdoor in its build scripts. The rules below make that kind of attack slow, visible and stoppable here. See [SECURITY.md](SECURITY.md) for the technical side.

- **Every change is reviewed by someone other than its author**, at every level, maintainers included.
- **Sensitive files always need Kenny's approval:** build and packaging scripts, CI workflows, config, plugins, licences, and anything the editor runs by itself. This holds however senior the author is.
- **Only Kenny publishes releases and holds the signing certificate.** Official builds come only from the itch.io page, signed and notarized.
- **Requirements for write access** (Triager and up): two-factor authentication on your GitHub account and signed commits.
- **Red flags** we watch for, from anyone: pressure to merge quickly or to add a maintainer; large changes to build scripts or tests that are hard to read; binary files or archives in code areas; new dependencies or downloaded tools; and changes that turn off checks. A red flag means a slower, closer review, never an accusation.
- **Access is reviewed every 3 months.** Roles that are no longer used are stepped down (see below).

## Stepping back and inactivity

Life happens. If you need to step back, say so and we'll note it.

Write access for anyone inactive for **about 3 months** is moved back to Contributor. This is routine housekeeping, not a judgement. You can ask to have it restored when you return.

Access can be removed immediately for:
- breaking the [Code of Conduct](CODE_OF_CONDUCT.md)
- knowingly adding assets that can't be shipped
- force-pushing over others' work
- misusing access in any way

## Decisions

- **Small decisions** (a bug fix, a prop, a tweak) are made in the pull request by the reviewer.
- **Bigger decisions** (new systems, map layout, story, monetisation, adding a platform) are discussed in an issue labelled `proposal`, and Kenny decides.
- **Releases** are cut by maintainers.

## Roadmap

The public roadmap lives in the repository's GitHub Projects tab.
