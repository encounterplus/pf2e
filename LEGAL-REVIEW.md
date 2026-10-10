# Publication and licensing review

Status: **ORC and OGL datasets reviewed; inherited system assets still on hold**

This document records a conservative publication boundary. It is not legal
advice. Policies and licenses can change, so their current text must be checked
again immediately before release.

## Recommended package split

1. **Community system package** — one installer containing schemas, forms,
   views, styling, scripts, generic Remaster mechanics, and the merged content
   from every reviewed source pack. ORC and OGL records keep explicit
   record-level license markers, and the package carries both complete notice
   sets. Aggregation does not relicense either dataset.
2. **Per-book ORC sources** — `compendium/packs` remains split by publication
   for review, attribution, rebuilding, and optional maintainer test packages;
   the normal community release does not install these alongside the merged
   system content because that would duplicate entity IDs.
3. **OGL source pack** — `compendium/ogl-packs/rage-of-elements` remains
   isolated in the repository for validation and attribution even though its
   records are bundled into the single user-facing system installer.
4. **Personal source modules** — content generated from purchased books,
   including extracted prose or art. These remain private and must not be
   committed or distributed.
5. **Experimental/personal features** — Remote Play and campaign-specific
   additions can live on a separate branch or in an optional add-on after the
   public base is stable.

The *Rage of Elements* source remains isolated under OGL 1.0a in
`compendium/ogl-packs`; it is not included in the ORC pack directory or
relicensed as ORC content.

## Current legal constraints

### Encounter+ upstream code

This work is derived from `https://github.com/encounterplus/pf2e` at commit
`832d839211c5d0354c8af2e85d7d9f938c1ff0dc`. No explicit license file was
present in that repository when this review was performed. Public visibility
does not by itself grant a general redistribution or relicensing right.

Before publishing binaries or a stand-alone copy, obtain clarification from
the Encounter+ maintainer about the license for the system code and assets.
Preserving the upstream Git history and attribution is required regardless.

### Paizo Community Use Policy

Paizo's Community Use Policy can cover freely available, non-commercial tools
and digital material that use Paizo intellectual property. A compliant project
must remain free and accessible without a paywall or unrelated access hurdles,
must carry Paizo's current required notice, must reproduce applicable author or
artist credits, and must provide visible up-to-date project contact
information. The policy also prohibits copying Paizo's trade dress.

The exact notice required by the policy as of the review date is:

> Pathfinder Second Edition Remaster system for Encounter+ uses trademarks
> and/or copyrights owned by Paizo Inc., used under Paizo's Community Use
> Policy (paizo.com/licenses/communityuse). We are expressly prohibited from
> charging you to use or access this content. Pathfinder Second Edition
> Remaster system for Encounter+ is not published, endorsed, or specifically
> approved by Paizo. For more information about Paizo Inc. and Paizo products,
> visit paizo.com.

The repository notice includes a monitored GitHub contact. Keep that contact
current, and do not claim Paizo or Encounter+ endorsement.

### ORC Remaster rules

The ORC License covers functional game expressions such as rules, statblocks,
traits, classes, spells, actions, equipment mechanics, and character-sheet
methods when they are Licensed Material. It excludes Reserved Material such as
trademarks, trade dress, visual art, settings, locations, plots, characters,
organizations, and other protected proper-name material unless separately
licensed.

Any public module containing ORC Licensed Material needs the ORC Required
Notice, good-faith attribution to upstream licensors/creators, a Reserved
Material statement, and a statement identifying any expressly designated
Licensed Material. Do not relicense OGL-only material as ORC content.

### OGL legacy material

OGL content and ORC content require separate compliance paths. The
Remaster-compatible *Rage of Elements* records therefore retain explicit
OGL 1.0a markers inside the aggregate system archive. That archive includes
the complete OGL 1.0a text, upstream Section 15 COPYRIGHT NOTICE, an Open Game
Content designation, a Product Identity designation, and a license map. The
records are never marked as ORC Licensed Material. Other OGL sources remain
excluded unless they receive the same source-specific review.

### Reference sites and structured staging data

Archives of Nethys publishes Paizo material under its own Community Use/OGL
notices and extensive source credits. Its public availability does not mean
that the site's compiled database, presentation, or API can automatically be
republished under an arbitrary software license. A public builder should fetch
only material independently permitted by the applicable Paizo/ORC/OGL terms,
retain source attribution, and avoid redistributing an AoN cache.

The private staging data used during development contained source-site IDs and
text extracted from owned PDFs. The public builder removes those fields and
publishes only the resulting ORC game mechanics and functional rules text. It
does not redistribute a source-site database or cache.

The PF2E for Foundry VTT project licenses its HTML/CSS/JavaScript under Apache
2.0, but its Pathfinder compendium content and art rely on separate Paizo and
Foundry licensing arrangements. The public packs therefore contain no Foundry
IDs, UUIDs, macros, art, or Foundry attribution claims.

### Public ORC content status

The ORC source allowlist currently contains 22 books whose Remaster editions
are identified as ORC releases. `Rage of Elements` is excluded from those ORC
packs and distributed separately under OGL 1.0a. Deity narrative,
creature/ancestry lore, class introductions,
setting prose, and background story prompts are also excluded as Reserved
Material or conservative publication holds.

The generated tree is checked for private extraction fields, email/watermark
patterns, Foundry identifiers and macros, deity records, license-boundary
errors, malformed collections, and missing source-specific notices.

## Asset hold

The current base inherits fonts, textures, a banner, and icons from the
Encounter+ upstream repository. No asset-license inventory accompanied that
repository. In particular, font files named FF Good, Gin, Sabon, and Taroca
must not be assumed redistributable. Book-like backgrounds and borders also
need review against the Community Use Policy's trade-dress restriction.

Before a public release, either:

- obtain and document redistribution permission for each asset; or
- replace it with an original or clearly open-licensed equivalent and record
  its license and source in an asset manifest.

## Publication checklist

- [ ] Encounter+ upstream code license confirmed in writing or in-repository
- [ ] every bundled font and image has a documented redistribution license
- [ ] Paizo trade-dress review completed for inherited system assets
- [x] current Community Use notice included and visible
- [x] project contact method included
- [x] ORC notices generated per ORC module; OGL-only source excluded from ORC packs
- [x] complete OGL 1.0a notice and Section 15 attribution included with the separately marked *Rage of Elements* records
- [x] ORC source author attribution included
- [x] public compendium scan rejects PDFs, watermarks, private fields, source-site IDs, and campaign data
- [x] no claim of endorsement by Paizo, Encounter+, Foundry, or Archives of Nethys
- [x] clean-room archive inspection passes before uploading a release
