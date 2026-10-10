{% if data.perception %}
**{{'Creature.Perception'|l}}** [{{data.perception|signed}}](roll "{{'Creature.Perception'|l}}"){% if data.senseEntries %}; {% for sense in data.senseEntries %}{% if sense.customText %}{{sense.customText}}{% else %}{% if sense.reference %}[{{sense.name}}](<{{sense.reference}}>){% else %}{{sense.name}}{% endif %}{% if sense.acuity %} ({% if sense.acuity == 'precise' %}[{{sense.acuity}}](/rule/precise-senses-rules-2406){% elif sense.acuity == 'imprecise' %}[{{sense.acuity}}](/rule/imprecise-senses-rules-2407){% elif sense.acuity == 'vague' %}[{{sense.acuity}}](/rule/vague-senses-rules-2408){% elif sense.acuityReference %}[{{sense.acuity}}](<{{sense.acuityReference}}>){% else %}{{sense.acuity}}{% endif %}){% endif %}{% if sense.details %} {{sense.details}}{% endif %}{% endif %}{% if not forloop.last %}, {% endif %}{% endfor %}{% else %}{% if data.senses %}; {{data.senses}}{% endif %}{% endif %}
{% endif %}

{% if data.recallKnowledge.dc %}
[**{{'Creature.RecallKnowledge'|l}}**](/action/recall-knowledge-player-core){% if data.recallKnowledge.entries %}—{% for entry in data.recallKnowledge.entries %}{{entry.subject|map: 'Trait'}}{% if entry.skills %} ({% for skill in entry.skills %}[{{skill|map: 'Skill'}}](/rule/{{skill}}-skill-player-core){% if not forloop.last %}, {% endif %}{% endfor %}){% endif %}{% if not forloop.last %}, {% endif %}{% endfor %}{% else %}{% if data.recallKnowledge.subjects %}—{% for subject in data.recallKnowledge.subjects %}{{subject|map: 'Trait'}}{% if not forloop.last %}, {% endif %}{% endfor %}{% if data.recallKnowledge.skills %} ({% for skill in data.recallKnowledge.skills %}[{{skill|map: 'Skill'}}](/rule/{{skill}}-skill-player-core){% if not forloop.last %}, {% endif %}{% endfor %}){% endif %}{% endif %}{% endif %}: DC {{data.recallKnowledge.dc}}
{% endif %}

{% if data.languages %}
[**{{'Creature.Languages'|l}}**](/rule/languages-rules-2080) {% for language in data.languages %}[{{language|map: 'Language'}}](/language/{{language}}){% if not forloop.last %}, {% endif %}{% endfor %}{% if data.languagesDetails %}; {{data.languagesDetails}}{% endif %}
{% endif %}

{% if data.skillsEditor.skills or data.skillsEditor.loreSkills %}
[**{{'Creature.Skills'|l}}**](/rule/skills-rules-2276) {% if data.skillsEditor.skills %}{% for key, value in data.skillsEditor.skills %}[{{ key|map: 'Skill' }}](/rule/{{key}}-skill-player-core) [{{value|signed}}](roll "{{ key|map: 'Skill' }}"){% if not forloop.last %}, {% endif %}{% endfor %}{% endif %}{% if data.skillsEditor.loreSkills %}{% if data.skillsEditor.skills %}, {% endif %}{% for skill in data.skillsEditor.loreSkills %}[{{skill.name}}](/rule/lore-skill-player-core) [{{skill.value|signed}}](roll "{{skill.name}}"){% if not forloop.last %}, {% endif %}{% endfor %}{% endif %}
{% else %}{% if data.skills or data.loreSkills %}
[**{{'Creature.Skills'|l}}**](/rule/skills-rules-2276) {% if data.skills %}{% for key, value in data.skills %}[{{ key|map: 'Skill' }}](/rule/{{key}}-skill-player-core) [{{value|signed}}](roll "{{ key|map: 'Skill' }}"){% if not forloop.last %}, {% endif %}{% endfor %}{% endif %}{% if data.loreSkills %}{% if data.skills %}, {% endif %}{% for skill in data.loreSkills %}[{{skill.name}}](/rule/lore-skill-player-core) [{{skill.value|signed}}](roll "{{skill.name}}"){% if not forloop.last %}, {% endif %}{% endfor %}{% endif %}
{% endif %}{% endif %}

**{{'Attribute.STR'|l|capitalize}}** [{{data.attributes.str|default: 0|signed}}](roll "{{'strength'|map: 'Attribute'}}") **{{'Attribute.DEX'|l|capitalize}}** [{{data.attributes.dex|default: 0|signed}}](roll "{{'dexterity'|map: 'Attribute'}}") **{{'Attribute.CON'|l|capitalize}}** [{{data.attributes.con|default: 0|signed}}](roll "{{'constitution'|map: 'Attribute'}}") **{{'Attribute.INT'|l|capitalize}}** [{{data.attributes.int|default: 0|signed}}](roll "{{'intelligence'|map: 'Attribute'}}") **{{'Attribute.WIS'|l|capitalize}}** [{{data.attributes.wis|default: 0|signed}}](roll "{{'wisdom'|map: 'Attribute'}}") **{{'Attribute.CHA'|l|capitalize}}** [{{data.attributes.cha|default: 0|signed}}](roll "{{'charisma'|map: 'Attribute'}}")

{% if data.itemEntries %}
**{{'Creature.Items'|l}}** {% for item in data.itemEntries %}{% if item.reference %}[{{item.name}}](<{{item.reference}}>){% else %}{{item.name}}{% endif %}{% if item.quantity %} ({{item.quantity}}){% endif %}{% if item.details %} {{item.details}}{% endif %}{% if not forloop.last %}, {% endif %}{% endfor %}
{% else %}{% if data.items %}
**{{'Creature.Items'|l}}** {{data.items}}
{% endif %}
{% endif %}

{% for ability in data.abilities.interaction %}
{% include "ability.md" %}
{% endfor %}
