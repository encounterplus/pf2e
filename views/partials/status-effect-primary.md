{% if duration != nil or durationType != nil %}**{{'StatusEffect.Duration'|l}}**{%if durationType != 'time' %} {{durationType|map: 'DurationType'}} {% else %} {{duration|format}} {{durationUnit|map: 'DurationUnit'}}{% endif %}{% endif %}

{% if source %}**{{'StatusEffect.Source'|l}}** {{sourceName}}{% endif %}

{% if enabled != nil and enabled == false %}**{{'StatusEffect.Enabled'|l}}** {{enabled}}{% endif %}

