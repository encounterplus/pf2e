{% if data.attributes %}
##### {{'Class.KeyAttribute'|l}}

**{{data.attributes|map: "Attribute", " or "}}**

At 1st level, your class gives you an ability boost to {{data.abilities|map: "Ability", " or "}}.
{% endif %}
---
{% if data.hp %}
##### {{'Common.HitPoints'|l}}

**{{data.hp}} plus your Constitution Modifier**

You increase your maximum number of HP by this number at 1st level and every level thereafter.
{% endif %}