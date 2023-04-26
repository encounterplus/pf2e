{% if data.perception %}
### Perception
{{data.perception|map: 'Proficiency'}} in Perception
{% endif %}

### Saving Throws
{{data.fortitude|map: 'Proficiency'|suffix: ' in Fortitude'}}
{{data.reflex|map: 'Proficiency'|suffix: ' in Reflex'}}
{{data.will|map: 'Proficiency'|suffix: ' in Will'}}

{% if data.skills%}
### Skills
{% for text in data.skills %}
{{text}}{% endfor %}
{% endif %}

{% if data.attacks %}
### Attacks
{% for text in data.attacks %}
{{text}}{% endfor %}
{% endif %}

{% if data.defenses %}
### Defenses
{% for text in data.defenses %}
{{text}}{% endfor %}
{% endif %}

{% if data.spells %}
### Spells
{% for text in data.spells %}
{{text}}{% endfor %}
{% endif %}

### Class DC

Trained in {{name|lowercase}} class DC
