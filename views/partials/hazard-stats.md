{% if data.complexity == 'simple' %}{% if data.stealthDC != nil %}**Stealth DC** {{data.stealthDC}}{% if data.stealthDetails %} {{data.stealthDetails}}{% endif %}
{% endif %}{% else %}{% if data.stealth != nil %}**Stealth** [{{data.stealth|signed}}](roll "Stealth"){% if data.stealthDetails %} {{data.stealthDetails}}{% endif %}
{% endif %}{% endif %}
{% if data.description %}**Description** {{data.description}}
{% endif %}
{% if data.disable %}**Disable** {{data.disable}}
{% endif %}
{% if data.hp.value > 0 %}---

{% if data.ac.value > 0 %}**{{'Common.AC'|l}}** {{data.ac.value}}{% if data.ac.details %} ({{data.ac.details}}){% endif %}; {% if data.saves.fortitude != nil %}**{{'SavingThrow.Fort'|l}}** [{{data.saves.fortitude|signed}}](roll "{{'SavingThrow.Fort'|l}}/save"); {% endif %}{% if data.saves.reflex != nil %}**{{'SavingThrow.Ref'|l}}** [{{data.saves.reflex|signed}}](roll "{{'SavingThrow.Ref'|l}}/save"){% endif %}{% endif %}{% if data.saves.will != nil and data.saves.will != 0 %}; **{{'SavingThrow.Wil'|l}}** [{{data.saves.will|signed}}](roll "{{'SavingThrow.Wil'|l}}/save"){% endif %}

{% if data.hardness > 0 or data.ac.value > 0 %}**{{'Item.Hardness'|l}}** {{data.hardness}}; {% endif %}**{{'Common.HP'|l}}** {{data.hp.value}}{% if data.hp.bt != nil %} (BT {{data.hp.bt}}){% endif %}{% if data.hp.details %} {{data.hp.details}}{% endif %}{% if data.immunities %}; **Immunities** {% for immunity in data.immunities %}{% if immunity == 'object immunities' %}[{{immunity}}](/rule/object-immunities-rules-2161){% else %}{{immunity}}{% endif %}{% if not forloop.last %}, {% endif %}{% endfor %}{% endif %}{% if data.weaknesses %}; **Weaknesses** {{data.weaknesses}}{% endif %}{% if data.resistances %}; **Resistances** {{data.resistances}}{% endif %}
{% endif %}
{% for ability in data.abilities %}{% include "hazard-vehicle-ability.md" %}
{% endfor %}
{% for ability in data.attacks %}{% include "attack.md" %}
{% endfor %}
{% if data.routine %}**Routine** {{data.routine}}
{% endif %}
{% if data.reset %}**Reset** {{data.reset}}
{% endif %}
