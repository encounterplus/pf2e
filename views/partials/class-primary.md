{% if data.abilities %}
**KEY ABILITY**

**{{data.abilities|map: "Ability", " or "}}**

At 1st level, your class gives you an ability boost to {{data.abilities|map: "Ability", " or "}}.
{% endif %}
---
{% if data.hp %}
**HIT POINTS**

**{{data.hp}} plus your Constitution Modifier**

You increase your maximum number of HP by this number at 1st level and every level thereafter.
{% endif %}

{% if data.size %}
**Size**
{{data.size|map: 'Size'}}
{% endif %}

{% if data.movement %}
**Speed**
{{data.movement}}
{% endif %}

{% if data.abilityBoosts %}
**Ability Boosts**
{{data.abilityBoosts|map: "Ability", "\n"}}
{% endif %}

{% if data.abilityFlaws %}
**Ability Flaws**
{{data.abilityFlaws|map: "Ability", "\n"}}
{% endif %}

{% if data.languages %}
**Languages**
{{data.languages|map: 'Language', "\n"}}
{% endif %}

{% if data.traits %}
**Traits**
{{data.traits|map: 'Trait', "\n"}}
{% endif %}

{% for feature in data.features %}
**{{feature.name}}**
{{feature.text}}
{% endfor %}