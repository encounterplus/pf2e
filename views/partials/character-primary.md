{% if data.ancestry or data.heritage or data.background or data.class %}
**{{'Character.Identity'|l}}** {% if data.ancestry %}{{data.ancestry}}{% endif %}{% if data.heritage %} ({{data.heritage}}){% endif %}{% if data.class %}; {{data.class}}{% endif %}{% if data.background %}; {{data.background}}{% endif %}{% if data.deity %}; {{data.deity}}{% endif %}
{% endif %}

**{{'Creature.Perception'|l}}** [{{data.perception|default: 0|signed}}](roll "{{'Creature.Perception'|l}}") {% if data.initiative != nil %}**{{'Character.Initiative'|l}}** [{{data.initiative|signed}}](roll "{{'Character.Initiative'|l}}"){% endif %}

**{{'Attribute.STR'|l}}** [{{data.attributes.str|default: 0|signed}}](roll "{{'Attribute.Strength'|l}}") **{{'Attribute.DEX'|l}}** [{{data.attributes.dex|default: 0|signed}}](roll "{{'Attribute.Dexterity'|l}}") **{{'Attribute.CON'|l}}** [{{data.attributes.con|default: 0|signed}}](roll "{{'Attribute.Constitution'|l}}") **{{'Attribute.INT'|l}}** [{{data.attributes.int|default: 0|signed}}](roll "{{'Attribute.Intelligence'|l}}") **{{'Attribute.WIS'|l}}** [{{data.attributes.wis|default: 0|signed}}](roll "{{'Attribute.Wisdom'|l}}") **{{'Attribute.CHA'|l}}** [{{data.attributes.cha|default: 0|signed}}](roll "{{'Attribute.Charisma'|l}}")

{% if data.skills %}
**{{'Creature.Skills'|l}}** {% for key, value in data.skills %}{{key|map: 'Skill'}} [{{value|signed}}](roll "{{key|map: 'Skill'}}"){% if not forloop.last %}, {% endif %}{% endfor %}
{% endif %}

{% if data.languages %}**{{'Common.Languages'|l}}** {% for language in data.languages %}{{language|map: 'Language'}}{% if not forloop.last %}, {% endif %}{% endfor %}{% endif %}
