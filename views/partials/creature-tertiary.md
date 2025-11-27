**{{'Common.Speed'|l}}** {{data.movement.walk}} feet, {% if data.movement.burrow %}burrow {{data.movement.burrow}} feet, {% endif %}{% if data.movement.climb %}climb {{data.movement.climb}} feet, {% endif %}{% if data.movement.fly %}fly {{data.movement.fly}} feet, {% endif %}{% if data.movement.swim %}swim {{data.movement.swim}} feet{% endif %}{% if data.movement.other %}; {{data.movement.other}}{% endif %}

{% for ability in data.attacks %}
{% include "attack.md" %}
{% endfor %}

{% for spellcasting in data.spellcasting %}
{% include "spellcasting.md" spellcasting %}
{% endfor %}

{% if data.rituals.type %}**{{data.rituals.type}}** {% endif %}{% if data.rituals %}**{{'Creature.Riutals'}}** {% if data.ritualsDC %}DC {{data.rituals.dc}}; {% endif %}{{data.rituals.text}}{% endif %}

{% for ability in data.abilities.offensive %}
{% include "ability.md" %}
{% endfor %}