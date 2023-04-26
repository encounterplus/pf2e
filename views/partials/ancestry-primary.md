{% if data.hp %}
### Hit Points
{{data.hp}}
{% endif %}

{% if data.size %}
### Size
{{data.size|map: 'Size'}}
{% endif %}

{% if data.movement %}
### Speed
{{data.movement}}
{% endif %}

{% if data.abilityBoosts %}
### Ability Boosts
{{data.abilityBoosts|map: "Ability", "\n"}}
{% endif %}

{% if data.abilityFlaws %}
### Ability Flaws
{{data.abilityFlaws|map: "Ability", "\n"}}
{% endif %}

{% if data.languages %}
### Languages
{{data.languages|map: 'Language', "\n"}}
{% endif %}

{% if data.traits %}
### Traits
{{data.traits|map: 'Trait', "\n"}}
{% endif %}

{% for feature in data.features %}
### {{feature.name}}
{{feature.text}}
{% endfor %}