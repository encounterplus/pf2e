{% if data.hp %}
##### {{'Common.HitPoints'|l}}
{{data.hp}}
{% endif %}

{% if data.size %}
##### {{'Common.Size'|l}}
{{data.size|map: 'Size'}}
{% endif %}

{% if data.movement %}
##### {{'Common.Speed'|l}}
{% include "movement.md" data.movement %}
{% endif %}

{% if data.attributeBoosts %}
##### {{'Ancestry.AttributeBoosts'|l}}
{{data.attributeBoosts|map: "Attribute", "\n"}}
{% endif %}

{% if data.attributeFlaws %}
##### {{'Ancestry.AttributeFlaws'|l}}
{{data.attributeFlaws|map: "Attribute", "\n"}}
{% endif %}

{% if data.languages %}
##### {{'Common.Languages'|l}}
{{data.languages|map: 'Language', "\n"}}
{% endif %}

{% if data.traits %}
##### {{'Common.Traits'|l}}
{{data.traits|map: 'Trait', "\n"}}
{% endif %}

{% for ability in data.abilities %}
##### {{ability.name}}
{{ability.text}}
{% endfor %}