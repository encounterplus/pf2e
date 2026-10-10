{% if data.traditionsText %}
**{{'Spell.Traditions'|l}}** {{data.traditionsText}}
{% endif %}

{% if data.requirements %}**{{'Spell.Requirements'|l}}** {{data.requirements}} {% endif %}

{% if data.cast %}**{{'Spell.Cast'|l}}** {{data.cast}}; {% endif %}{% if data.cost %}**{{'Spell.Cost'|l}}** {{data.cost}}; {% endif %}{% if data.trigger %}**{{'Spell.Trigger'|l}}** {{data.trigger}}{% endif %}

{% if data.range %}**{{'Spell.Range'|l}}** {{data.range|lowercase}}; {% endif %}{% if data.area %}**{{'Spell.Area'|l}}** {{data.area|lowercase}}; {% endif %}{% if data.targets %}**{{'Spell.Targets'|l}}** {{data.targets}} {% endif %}

{% if data.defense %}**{{'Spell.Defense'|l}}** {{data.defense|map: 'SpellDefense'}}; {% endif %}{% if data.durationText %}**{{'Spell.Duration'|l}}** {{data.durationText|lowercase}}{% else %}{% if data.duration or data.durationType %}**{{'Spell.Duration'|l}}** {% if data.durationType or data.durationUnit %}{% include 'spell-effect-duration.md' %}{% else %}{{data.duration|lowercase}}{% endif %}{% endif %}{% endif %}
