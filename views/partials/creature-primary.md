{% if data.perception %}
**Perception** {{data.perception|signed}}; {{data.senses}}
{% endif %}

{% if data.languages %}
**Languages** {{data.languages|map: 'Language'}}
{% endif %}

{% if data.skills %}
**Skills** {% for key, value in data.skills %}{{ key|map: 'Skill' }} {{value|signed}}, {% endfor %}
{% endif %}

**Str** {{data.str|signed|default: '+0'}} **Dex** {{data.dex|signed|default: '+0'}} **Con** {{data.con|signed|default: '+0'}} **Int** {{data.int|signed|default: '+0'}} **Wis** {{data.wis|signed|default: '+0'}} **Cha** {{data.cha|signed|default: '+0'}}

{% if data.items %}
**Items** {{data.items|join:', '}}
{% endif %}

{% for ability in data.interactionAbilities %}
{% include "ability.md" %}
{% endfor %}