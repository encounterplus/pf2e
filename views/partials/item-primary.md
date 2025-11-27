{% if data.price %}**{{'Item.Price'|l}}** {{data.price}}{% endif %}

{% if data.ammunition %}**{{'Item.Ammunition'|l}}** {{data.ammunition}}{% endif -%}
{% if data.usage %}**{{'Item.Usage'|l}}** {{data.usage}} {% endif -%}

{% if data.ac != nil %}**{{'Item.AcBonus'|l}}** {{data.ac|signed}} {% endif -%}
{% if data.dexCap != nil %}**{{'Item.DexCap'|l}}** {{data.dexCap|signed}} {% endif -%}
{% if data.checkPenalty != nil %}**{{'Item.CheckPenalty'|l}}** {{data.checkPenalty|signed}} {% endif -%}
{% if data.speedPenalty != nil %}**{{'Item.SpeedPenalty'|l}}** {{data.speedPenalty|signed}} ft. {% endif -%}
{% if data.hardness != nil %}**{{'Item.Hardness'|l}}** {{data.hardness}} {% endif -%}
{% if data.hp != nil %}**{{'Common.HP'|l}}** {{data.hp}} {{data.bt|brackets}} {% endif -%}

{% if data.damage != nil %}**{{'Common.Damage'|l}}** {{data.damage}} {% endif -%}

{% if data.str != nil %}**{{'Attribute.Strength'|l}}** {{data.str|signed}} {% endif -%}
{% if data.bulk %}**{{'Item.Bulk'|l}}** {{data.bulk}} {% endif -%}

{% if data.range != nil %}**{{'Common.Range'|l}}** {{data.range}} ft. {% endif -%}
{% if data.reload != nil %}**{{'Item.Reload'|l}}** {{data.reload}} {% endif -%}
{% if data.hands != nil %}**{{'Item.Hands'|l}}** {{data.hands}} {% endif %}


{% if data.weaponType %}**{{'Common.Type'|l}}** {{data.weaponType|map: 'WeaponType'}} {% endif %}{% if data.weaponCategory %}**{{'Common.Category'|l}}** {{data.weaponCategory|map: 'WeaponCategory'}} {% endif %}{% if data.weaponGroup %}**{{'Common.Group'|l}}** {{data.weaponGroup|map: 'WeaponGroup'}} {% endif %}

{% if data.armorCategory %}**{{'Common.Category'|l}}** {{data.armorCategory|map: 'ArmorCategory'}} {% endif %}{% if data.armorGroup %}**{{'Common.Group'|l}}** {{data.armorGroup|map: 'ArmorGroup'}} {% endif %}

{% if data.activation %}**{{'Item.Activate'|l}}** {% if data.activation.actions %}![{{data.activation.actions}}](icons/actions/{{data.activation.actions}}.png#height=18) {% endif %}{% if data.activation.type %}{{data.activation.type}} {% endif %}{% if data.activation.traits %}({{data.activation.traits|map: 'Trait'|lowercase}}); {% endif %}{% endif %} {% if data.activation.text %}{{data.activation.text}}{% endif %}

{% if data.onset %}**{{'Item.Onset'|l}}** {{data.onset}}{% endif %}