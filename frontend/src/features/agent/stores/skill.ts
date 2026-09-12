import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { Skill } from '../types/agent';

export const useSkillStore = defineStore('skill', () => {
  const skills = ref<Skill[]>([]);
  const activeSkill = ref<string>('');
  const showSkillMenu = ref(false);

  const setSkills = (list: Skill[]) => {
    skills.value = list;
  };

  const setActiveSkill = (name: string) => {
    activeSkill.value = name;
  };

  const clearActiveSkill = () => {
    activeSkill.value = '';
  };

  const toggleSkillMenu = (show: boolean) => {
    showSkillMenu.value = show;
  };

  const installSkill = (id: string) => {
    const s = skills.value.find(sk => sk.id === id);
    if (s) s.installed = true;
  };

  const uninstallSkill = (id: string) => {
    const s = skills.value.find(sk => sk.id === id);
    if (s) s.installed = false;
  };

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
