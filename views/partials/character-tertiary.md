{% if data.movement %}**{{'Common.Speed'|l}}** {% include "movement.md" data.movement %}{% endif %}

{% for ability in data.attacks %}
{% include "attack.md" %}
{% endfor %}

{% for spellcasting in data.spellcasting %}
{% include "spellcasting.md" spellcasting %}
{% endfor %}

{% if data.items %}**{{'Creature.Items'|l}}** {{data.items}}{% endif %}
