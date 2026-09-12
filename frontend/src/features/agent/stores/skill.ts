import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { Skill } from '../types/agent';

export const useSkillStore = defineStore('skill', () => {
  const skills = ref<Skill[]>([]);
  const activeSkill = ref<string>('');
  const showSkillMenu = ref(false);

  function setSkills(list: Skill[]) {
    skills.value = list;
  }

  function setActiveSkill(name: string) {
    activeSkill.value = name;
  }

  function clearActiveSkill() {
    activeSkill.value = '';
  }

  function toggleSkillMenu(show: boolean) {
    showSkillMenu.value = show;
  }

  function installSkill(id: string) {
    const s = skills.value.find(sk => sk.id === id);
    if (s) s.installed = true;
  }

  function uninstallSkill(id: string) {
    const s = skills.value.find(sk => sk.id === id);
    if (s) s.installed = false;
  }

  return {
    skills,
    activeSkill,
    showSkillMenu,
    setSkills,
    setActiveSkill,
    clearActiveSkill,
    toggleSkillMenu,
    installSkill,
    uninstallSkill,
  };
});
