{% if data.muse %}**{{'Spell.Muse'|l}}** {{data.muse}}{% endif %}

{% if data.traditions %}
**{{'Spell.Traditions'|l}}** {{data.traditions|map: 'MagicalTradition'|lowercase}}
{% endif %}

{% if data.trigger %}**{{'Spell.Trigger'|l}}** {{data.trigger}} {% endif %}{% if data.requirements %}**{{'Spell.Requirements'|l}}** {{data.requirements}} {% endif %}

{% if data.cast %}**{{'Spell.Cast'|l}}** {{data.cast}}; {% endif %}{% if data.cost %}**{{'Spell.Cost'|l}}** {{data.cost}}; {% endif %}

{% if data.range %}**{{'Spell.Range'|l}}** {{data.range|lowercase}}; {% endif %}{% if data.area %}**{{'Spell.Area'|l}}** {{data.area|lowercase}}; {% endif %}{% if data.targets %}**{{'Spell.Targets'|l}}** {{data.targets}} {% endif %}

{% if data.defense %}**{{'Spell.Defense'|l}}** {{data.defense|map: 'SpellDefense'}}; {% endif %}{% if data.duration %}**{{'Spell.Duration'|l}}** {{data.duration|lowercase}}{% endif %}

