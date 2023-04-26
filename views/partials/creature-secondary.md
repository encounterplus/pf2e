{% if data.ac %}**AC** {{data.ac}}{% if data.acDetail %} ({{data.acDetail}}){% endif %}; {% endif %}{% if data.fort %}**Fort** {{data.fort}}, {% endif %}{% if data.ref %}**Ref** {{data.ref}}, {% endif %}{% if data.will %}**Will** {{data.will}}{% endif %}{% if data.saveDetail %}; {{data.saveDetail}}{% endif %}

{% if data.hp %}**HP** {{data.hp}}{% if data.hpDetail %}, {{data.hpDetail}}{% endif %}{% endif %}; {% if data.immunities %}**Immunities** {{data.immunities|join:', '}}; {% endif %}{% if data.weaknesses %}**Weaknesses** {% for key, value in data.weaknesses %}{{ key|map: 'Damage' }} {{value}}{% if not forloop.last %}, {% endif %}{% endfor %}; {% endif %}{% if data.resistances %}**Resistances** {% for key, value in data.resistances %}{{ key|map: 'Damage' }} {{value}}{% if not forloop.last %}, {% endif %}{% endfor %}{% endif %}

{% for ability in data.defensiveAbilities %}
{% include "ability.md" %}
{% endfor %}