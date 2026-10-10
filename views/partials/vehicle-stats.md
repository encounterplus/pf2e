{% if data.price %}**{{'Item.Price'|l}}** {{data.price}}
{% endif %}
{% if data.description %}---

{{data.description}}

---

{% endif %}
{% if data.space.long %}**Space** {{data.space.long}} feet long × {{data.space.wide}} feet wide × {{data.space.high}} feet high
{% endif %}
{% if data.crew %}**Crew** {{data.crew}}{% endif %}{% if data.passengers %}; **Passengers** {{data.passengers}}{% endif %}

{% if data.pilotingCheck %}**Piloting Check** {{data.pilotingCheck}}
{% endif %}
{% if data.hp.value > 0 %}---

{% if data.ac.value != nil %}**{{'Common.AC'|l}}** {{data.ac.value}}{% if data.ac.details %} ({{data.ac.details}}){% endif %}{% endif %}{% if data.fortitude != nil %}; **{{'SavingThrow.Fort'|l}}** [{{data.fortitude|signed}}](roll "{{'SavingThrow.Fort'|l}}/save"){% endif %}

{% if data.hardness != nil %}**{{'Item.Hardness'|l}}** {{data.hardness}}; {% endif %}**{{'Common.HP'|l}}** {{data.hp.value}}{% if data.hp.bt != nil %} (BT {{data.hp.bt}}){% endif %}{% if data.hp.details %} {{data.hp.details}}{% endif %}{% if data.immunities %}; **Immunities** {% for immunity in data.immunities %}{% if immunity == 'object immunities' %}[{{immunity}}](/rule/object-immunities-rules-2161){% else %}{{immunity}}{% endif %}{% if not forloop.last %}, {% endif %}{% endfor %}{% endif %}{% if data.weaknesses %}; **Weaknesses** {{data.weaknesses}}{% endif %}{% if data.resistances %}; **Resistances** {{data.resistances}}{% endif %}
{% endif %}
{% if data.speed or data.collisionDC %}---

{% endif %}{% if data.speed %}**{{'Common.Speed'|l}}** {{data.speed}}
{% endif %}
{% if data.collisionDamage %}**Collision** {{data.collisionDamage|roll: 'Collision', 'damage'}}{% if data.collisionDC > 0 %} (DC {{data.collisionDC}}){% endif %}
{% endif %}
{% for ability in data.abilities %}{% include "hazard-vehicle-ability.md" %}
{% endfor %}
