{% if data.areasOfConcern %}**Areas of Concern** {% if data.areasOfConcern in data.deityReferenceKeys.areasOfConcern %}{% for reference in data.deityReferences.areasOfConcern %}{% if reference.value == data.areasOfConcern %}{{reference.text}}{% endif %}{% endfor %}{% else %}{{data.areasOfConcern}}{% endif %}{% endif %}

{% if data.deityDirectiveFormat == 'text' or data.edictsText != nil %}{% if data.edictsText %}**Edicts** {{data.edictsText}}{% endif %}{% else %}{% if data.edicts %}**Edicts** {% for value in data.edicts %}{% if value in data.deityReferenceKeys.edicts %}{% for reference in data.deityReferences.edicts %}{% if reference.value == value %}{{reference.text}}{% endif %}{% endfor %}{% else %}{{value}}{% endif %}{% if not forloop.last %}; {% endif %}{% endfor %}{% endif %}{% endif %}

{% if data.deityDirectiveFormat == 'text' or data.anathemaText != nil %}{% if data.anathemaText %}**Anathema** {{data.anathemaText}}{% endif %}{% else %}{% if data.anathema %}**Anathema** {% for value in data.anathema %}{% if value in data.deityReferenceKeys.anathema %}{% for reference in data.deityReferences.anathema %}{% if reference.value == value %}{{reference.text}}{% endif %}{% endfor %}{% else %}{{value}}{% endif %}{% if not forloop.last %}; {% endif %}{% endfor %}{% endif %}{% endif %}

{% if data.divineAttribute %}[**Divine Attribute**](/background/raised-by-belief-player-core) {% for value in data.divineAttribute %}{{value|map: 'DeityAttribute'}}{% if not forloop.last %}; {% endif %}{% endfor %}{% endif %}

{% if data.divineAttributeNotes %}**Divine Attribute Notes** {{data.divineAttributeNotes}}{% endif %}

{% if data.clericFont %}**Divine Font** {% for value in data.clericFont %}{% if value in data.deityReferenceKeys.clericFont %}{% for reference in data.deityReferences.clericFont %}{% if reference.value == value %}{{reference.text}}{% endif %}{% endfor %}{% else %}{{value}}{% endif %}{% if not forloop.last %}; {% endif %}{% endfor %}{% endif %}

{% if data.deitySanctificationFormat == 'text' or data.sanctificationText != nil %}{% if data.sanctificationText %}**Sanctification** {{data.sanctificationText}}{% endif %}{% else %}{% if data.sanctification %}**Sanctification** {{data.sanctification|map: 'Sanctification'}}{% else %}
{% if data.sanctificationOptions %}**Sanctification** {% for value in data.sanctificationOptions %}{% if value in data.deityReferenceKeys.sanctificationOptions %}{% for reference in data.deityReferences.sanctificationOptions %}{% if reference.value == value %}{{reference.text}}{% endif %}{% endfor %}{% else %}{{value}}{% endif %}{% if not forloop.last %}; {% endif %}{% endfor %}{% endif %}

{% endif %}{% endif %}

{% if data.divineSkill %}**Divine Skill** {% if data.divineSkill in data.deityReferenceKeys.divineSkill %}{% for reference in data.deityReferences.divineSkill %}{% if reference.value == data.divineSkill %}{{reference.text}}{% endif %}{% endfor %}{% else %}{% set skillName %}{{data.divineSkill|lowercase}}{% endset %}{% set skillRoute %}{{skillName|valueMap: 'SkillReference'}}{% endset %}{% if skillRoute and skillRoute != skillName %}[{{data.divineSkill|map: 'Skill'}}](<{{skillRoute}}>){% else %}{{data.divineSkill|map: 'Skill'}}{% endif %}{% endif %}{% endif %}

{% if data.favoredWeapon %}**Favored Weapon** {% for value in data.favoredWeapon %}{% if value in data.deityReferenceKeys.favoredWeapon %}{% for reference in data.deityReferences.favoredWeapon %}{% if reference.value == value %}{{reference.text}}{% endif %}{% endfor %}{% else %}{{value}}{% endif %}{% if not forloop.last %}; {% endif %}{% endfor %}{% endif %}

{% if data.domains %}**Domains** {% for value in data.domains %}{% if value in data.deityReferenceKeys.domains %}{% for reference in data.deityReferences.domains %}{% if reference.value == value %}{{reference.text}}{% endif %}{% endfor %}{% else %}{{value}}{% endif %}{% if not forloop.last %}; {% endif %}{% endfor %}{% endif %}

{% if data.alternateDomains %}**Alternate Domains** {% for value in data.alternateDomains %}{% if value in data.deityReferenceKeys.alternateDomains %}{% for reference in data.deityReferences.alternateDomains %}{% if reference.value == value %}{{reference.text}}{% endif %}{% endfor %}{% else %}{{value}}{% endif %}{% if not forloop.last %}; {% endif %}{% endfor %}{% endif %}

{% if data.spells %}**Cleric Spells** {% for value in data.spells %}{% if value in data.deityReferenceKeys.spells %}{% for reference in data.deityReferences.spells %}{% if reference.value == value %}{{reference.text}}{% endif %}{% endfor %}{% else %}{{value}}{% endif %}{% if not forloop.last %}; {% endif %}{% endfor %}{% endif %}
