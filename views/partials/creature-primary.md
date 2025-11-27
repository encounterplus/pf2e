{% if data.perception %}
**{{'Creature.Perception'|l}}** [{{data.perception|signed}}](roll "{{'Creature.Perception'|l}}"); {{data.senses}}
{% endif %}

{% if data.languages %}
**{{'Creature.Languages'|l}}** {{data.languages|map: 'Language'}}
{% endif %}

{% if data.skills %}
**{{'Creature.Skills'|l}}** {% for key, value in data.skills %}{{ key|map: 'Skill' }} [{{value|signed}}](roll "{{ key|map: 'Skill' }}"), {% endfor %}
{% endif %}

**{{'Attribute.STR'|l|capitalize}}** [{{data.attributes.str|default: 0|signed}}](roll "{{'str'|map: 'Attribute'}}") **{{'Attribute.DEX'|l|capitalize}}** [{{data.attributes.dex|default: 0|signed}}](roll "{{'dex'|map: 'Attribute'}}") **{{'Attribute.CON'|l|capitalize}}** [{{data.attributes.con|default: 0|signed}}](roll "{{'con'|map: 'Attribute'}}") **{{'Attribute.INT'|l|capitalize}}** [{{data.attributes.int|default: 0|signed}}](roll "{{'int'|map: 'Attribute'}}") **{{'Attribute.WIS'|l|capitalize}}** [{{data.attributes.wis|default: 0|signed}}](roll "{{'wis'|map: 'Attribute'}}") **{{'Attribute.CHA'|l|capitalize}}** [{{data.attributes.cha|default: 0|signed}}](roll "{{'cha'|map: 'Attribute'}}")

{% if data.items %}
**{{'Creature.Items'|l}}** {{data.items}}
{% endif %}

{% for ability in data.abilities.interaction %}
{% include "ability.md" %}
{% endfor %}