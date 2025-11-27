{% if data.traditions %}
**{{'Spell.Traditions'|l}}** {{data.traditions|map: 'MagicalTradition'|lowercase}}
{% endif %}

{% if data.cast %}**{{'Spell.Cast'|l}}** {{data.cast}}; {% endif %}{% if data.trigger %}**{{'Spell.Trigger'|l}}** {{data.trigger}}{% endif %}

{% if data.range %}**{{'Spell.Range'|l}}** {{data.range}}; {% endif %}{% if data.area %}**{{'Spell.Area'|l}}** {{data.area}}; {% endif %}{% if data.targets %}**{{'Spell.Targets'|l}}** {{data.targets}} {% endif %}

{% if data.defense %}**{{'Spell.Defense'|l}}** {{data.defense}}; {% endif %}{% if data.duration %}**{{'Spell.Duration'|l}}** {{data.duration}}{% endif %}

