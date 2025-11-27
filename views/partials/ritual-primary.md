{% if data.cast %}**{{'Spell.Cast'|l}}** {{data.cast}}; {% endif %}{% if data.cost %}**{{'Spell.Cost'|l}}** {{data.cost}}; {% endif %}{% if data.secondaryCasters %}**{{'Ritual.SecondaryCasters'|l}}** {{data.secondaryCasters}}{% endif %}

{% if data.primaryChecks %}**{{'Ritual.PrimaryChecks'|l}}** {{data.primaryChecks}}; {% endif %}{% if data.secondaryChecks %}**{{'Ritual.SecondaryChecks'|l}}** {{data.secondaryChecks}} {% endif %}

{% if data.range %}**{{'Spell.Range'|l}}** {{data.range}}; {% endif %}{% if data.area %}**{{'Spell.Area'|l}}** {{data.area}}; {% endif %}{% if data.targets %}**{{'Spell.Targets'|l}}** {{data.targets}} {% endif %}

{% if data.duration %}**{{'Spell.Duration'|l}}** {{data.duration}}{% endif %}

