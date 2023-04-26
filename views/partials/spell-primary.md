{% if data.traditions %}
**Traditions** {{data.traditions|map: 'MagicalTradition'|lowercase}}
{% endif %}

{% if data.components or data.actions or data.time %}
**Cast** {% if data.actions %}![Action](/icons/Action/{{data.actions}}.png#height=18) {% else %}{{data.time}} {% endif %}{{data.components|map: 'SpellComponent'|lowercase}}
{% endif %}

{% if data.range %}**Range** {{data.range}} feet; {% endif %}{% if data.areaEffectSize %}**Area** {{data.areaEffectSize}}-foot {{data.areaEffectShape|map: 'AreaEffectShape'|lowercase}}; {% endif %}{% if data.targets %}**Targets** {{data.targets}}; {% endif %}

{% if data.savingThrow %}**Saving Throw** {{data.savingThrow}}; {% endif %}{% if data.duration %}**Duration** {{data.duration}}{% endif %}

