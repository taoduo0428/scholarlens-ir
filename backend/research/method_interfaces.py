"""Extract an explicitly named and typed method input or output from an author statement."""

import re

from backend.research.research_profile import NEGATED, attribution


_OWNER = r"Our (?:method|algorithm|model|procedure) "
_ARGUMENT = (
    r"(?:an? |the )?(?P<item>(?:[\w-]+ ){1,5}"
    r"(?:matrix|vector|tensor|map|series|sequence|table|graph|spectrum|image|profile)"
    r" (?:in|encoded as) [\w%/-]+(?: per [\w-]+)?)"
)
_ROLES = {
    "produces": re.compile(_OWNER + r"(?:outputs|produces|returns) " + _ARGUMENT + r"\.", re.I),
    "requires": re.compile(_OWNER + r"(?:requires|takes|accepts) " + _ARGUMENT + r" as (?:its |an? )?input\.", re.I),
}
_AMBIGUOUS = re.compile(r"\b(?:not|no|only|some|another|such|above|their|baseline|example|either|or|and|without|"
                        r"could|might|may|if|unless|usually|optionally|hypothetical)\b", re.I)


def interface(statement):
    if NEGATED.search(statement) or _AMBIGUOUS.search(statement) or attribution(statement)[0] != "authors":
        return None
    for role, pattern in _ROLES.items():
        match = pattern.fullmatch(statement)
        if match:
            # Unit symbols and format names are case-sensitive (e.g. mW and MW).
            return role, match["item"]
    return None
