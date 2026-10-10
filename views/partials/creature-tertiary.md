**{{'Common.Speed'|l}}** {% if data.movement.walk %}{{data.movement.walk}} {{'Common.Feet'|l|lowercase}},{% endif %}{% if data.movement.burrow %} {{'Movement.Burrow'|l|lowercase}} {{data.movement.burrow}} {{'Common.Feet'|l|lowercase}},{% endif %}{% if data.movement.climb %} {{'Movement.Climb'|l|lowercase}} {{data.movement.climb}} {{'Common.Feet'|l|lowercase}},{% endif %}{% if data.movement.fly %} {{'Movement.Fly'|l|lowercase}} {{data.movement.fly}} {{'Common.Feet'|l|lowercase}},{% endif %}{% if data.movement.swim %} {{'Movement.Swim'|l|lowercase}} {{data.movement.swim}} {{'Common.Feet'|l|lowercase}}{% endif %}{% if data.movement.other %}; {{data.movement.other}}{% endif %}

{% for ability in data.attacks %}
{% include "attack.md" %}
{% endfor %}

{% for spellcasting in data.spellcasting %}
{% include "spellcasting.md" spellcasting %}
{% endfor %}

{% if data.ritualcasting %}{% for ritualcasting in data.ritualcasting %}{% if ritualcasting.type %}**{{ritualcasting.type}}** {% else %}**{{'Creature.Rituals'|l}}** {% endif %}{% if ritualcasting.dc %}{{'Common.DC'|l}} {{ritualcasting.dc}}; {% endif %}{% if ritualcasting.ritualGroups %}{% for group in ritualcasting.ritualGroups %}**{{group.label}}** {% for ritual in group.rituals %}{% if ritual.reference %}[{{ritual.name}}](<{{ritual.reference}}>){% else %}{{ritual.name}}{% endif %}{% if ritual.details %} ({{ritual.details}}){% endif %}{% if not forloop.last %}, {% endif %}{% endfor %}{% if not forloop.last %}; {% endif %}{% endfor %}{% else %}{{ritualcasting.text}}{% endif %}{% if not forloop.last %}
{% endif %}{% endfor %}{% else %}{% if data.rituals %}{% if data.rituals.type %}**{{data.rituals.type}}** {% else %}**{{'Creature.Rituals'|l}}** {% endif %}{% if data.rituals.dc %}{{'Common.DC'|l}} {{data.rituals.dc}}; {% endif %}{% if data.rituals.ritualGroups %}{% for group in data.rituals.ritualGroups %}**{{group.label}}** {% for ritual in group.rituals %}{% if ritual.reference %}[{{ritual.name}}](<{{ritual.reference}}>){% else %}{{ritual.name}}{% endif %}{% if ritual.details %} ({{ritual.details}}){% endif %}{% if not forloop.last %}, {% endif %}{% endfor %}{% if not forloop.last %}; {% endif %}{% endfor %}{% else %}{{data.rituals.text}}{% endif %}{% endif %}{% endif %}

{% for ability in data.abilities.offensive %}
{% include "ability.md" %}
{% endfor %}
