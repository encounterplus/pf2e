{{data.ac|field: '**AC Bonus**','; '}}
{{data.checkPenalty|signed|field: '**Check Penalty**','; '}}
{{data.speedPenalty|signed|field: '**Speed Penalty**',' ft.; '}}
{{data.dex|field: '**Dex Cap**','; '}}
{{data.strength|field: '**Strength**',';'}}
{{data.bulk|field: '**Bulk**','; '}}

{{data.damage|field: '**Damage**','; '}}
{{data.bulk|field: '**Bulk**','; '}}
{{data.hands|field: '**Hands**','; '}}
{{data.range|field: '**Range**',' ft.; '}}
{{data.reload|field: '**Reload**','; '}}
{{data.weaponTraits|join: ', '|field: '**Weapon Traits**','; '}}

{{data.price|field: '**Price**',' gp; '}}
{{data.ammunition|field: '**Ammunition**','; '}}
{{data.usage|field: '**Usage**','; '}}{{data.bulk|field: '**Bulk**'}}

{% if data.activation %}**Activate** {% if data.activation.actions %}![Action](/icons/Action/{{data.activation.actions}}.png#height=18) {% endif %}{{data.activation.components|map: 'ItemActivationComponent'}} {% if data.activation.traits %}({{dadta.activation.traits|map: 'Trait'|lowercase}}); {% endif %}{% endif %} {{data.onset|field: '**Onset**'}}