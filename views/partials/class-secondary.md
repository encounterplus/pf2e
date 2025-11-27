{% if data.perception %}
#### {{'Common.Perception'|l}}
{{data.perception|map: 'Proficiency'}} in Perception
{% endif %}

#### {{'Common.SavingThrows'|l}}
{% if data.fortitude %}{{data.fortitude|map: 'Proficiency'}} in Fortitude{% endif %}
{% if data.reflex %}{{data.reflex|map: 'Proficiency'}} in Reflex'{% endif %}
{% if data.will %}{{data.will|map: 'Proficiency'}} in Will{% endif %}

{% if data.skills %}
#### {{'Common.Skills'|l}}
{{data.skills}}
{% endif %}

{% if data.attacks %}
#### {{'Common.Attacks'|l}}
{{data.attacks}}
{% endif %}

{% if data.defenses %}
#### {{'Common.Defenses'|l}}
{{data.defenses}}
{% endif %}

{% if data.spells %}
#### {{'Common.Spells'|l}}
{{data.spells}}
{% endif %}

#### {{'Class.ClassDC'|l}}

Trained in {{name|lowercase}} class DC
